use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::sync::oneshot;

const CREATE_NO_WINDOW: u32 = 0x08000000;
const MAX_FRAME: usize = 16_100_000;
const MAX_PENDING: usize = 24;
const LOG_SUFFIX: &str = ".stderr.log";

#[derive(Serialize)]
struct Request<'a> {
    id: u64,
    method: &'static str,
    target: &'a str,
    body: Option<&'a str>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Response {
    pub status: u16,
    pub data: Value,
}

#[derive(Deserialize)]
#[serde(untagged)]
enum Frame {
    Ready {
        ready: u8,
        pid: u32,
    },
    Response {
        id: u64,
        #[serde(flatten)]
        response: Response,
    },
}

#[derive(Default)]
struct Replies {
    pending: HashMap<u64, oneshot::Sender<Response>>,
    closed: bool,
}

pub struct Backend {
    child: Mutex<Option<Child>>,
    input: Arc<Mutex<Option<ChildStdin>>>,
    replies: Arc<Mutex<Replies>>,
    next_id: AtomicU64,
    log_path: PathBuf,
    chinese: bool,
    pub pid: u32,
}

impl Backend {
    pub fn start(
        release: &Path,
        engine: &Path,
        data: &Path,
        game: Option<&Path>,
        chinese: bool,
    ) -> Result<Self, String> {
        let directory = data.join("logs");
        fs::create_dir_all(&directory).map_err(|err| err.to_string())?;
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default();
        let log_path = directory.join(format!(
            "tauri-{}-{}{}",
            now.as_millis(),
            std::process::id(),
            LOG_SUFFIX
        ));
        let log_error = |message: String| format!("{message}\n{}", log_path.display());
        let python = release.join("python/python.exe");
        let entry = release.join("source/desktop_server.py");
        let mut log = OpenOptions::new()
            .append(true)
            .create_new(true)
            .open(&log_path)
            .map_err(|err| log_error(err.to_string()))?;
        writeln!(
            log,
            "Transport: anonymous pipes\nPython: {}\nWorking directory: {}\nGame directory: {}",
            python.display(),
            engine.display(),
            game.map_or_else(
                || "saved configuration / auto-detect".into(),
                |p| p.display().to_string()
            )
        )
        .map_err(|err| log_error(err.to_string()))?;

        let mut command = Command::new(&python);
        for (key, _) in std::env::vars_os() {
            if key
                .to_string_lossy()
                .to_ascii_uppercase()
                .starts_with("FM27_")
            {
                command.env_remove(key);
            }
        }
        if let Some(game) = game {
            command.env("FM27_GAME_ROOT", game);
        }
        let mut child = command
            .args(["-E", "-s", "-B", "-u", "-X", "utf8", "-X", "faulthandler"])
            .arg(entry)
            .arg("--stdio")
            .env("FM27_ENGINE_ROOT", engine)
            .env("FM27_DESKTOP_DATA", data)
            .env("FM27_UI_LANGUAGE", if chinese { "zh-CN" } else { "en" })
            .current_dir(engine)
            .creation_flags(CREATE_NO_WINDOW)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::from(
                log.try_clone().map_err(|err| log_error(err.to_string()))?,
            ))
            .spawn()
            .map_err(|err| log_error(err.to_string()))?;
        let pid = child.id();
        let input = child.stdin.take().expect("piped stdin");
        let output = child.stdout.take().expect("piped stdout");
        let (ready, startup) = mpsc::sync_channel(1);
        let replies = Arc::new(Mutex::new(Replies::default()));
        let read_replies = Arc::clone(&replies);
        let backend = Self {
            child: Mutex::new(Some(child)),
            input: Arc::new(Mutex::new(Some(input))),
            replies,
            next_id: AtomicU64::new(1),
            log_path: log_path.clone(),
            chinese,
            pid,
        };

        thread::Builder::new()
            .name("fm27-backend-output".into())
            .spawn(move || {
                let mut reader = BufReader::new(output);
                let mut line = Vec::new();
                let mut startup = Some(ready);
                loop {
                    line.clear();
                    match reader.read_until(b'\n', &mut line) {
                        Ok(0) => break,
                        Ok(_) => {}
                        Err(err) => {
                            let _ = writeln!(log, "IPC read error: {err}");
                            break;
                        }
                    }
                    match serde_json::from_slice(&line) {
                        Ok(Frame::Ready {
                            ready: 1,
                            pid: reported,
                        }) if reported == pid => {
                            if let Some(sender) = startup.take() {
                                let _ = sender.send(());
                                let _ = writeln!(log, "Backend ready. PID: {pid}");
                            }
                        }
                        Ok(Frame::Response { id, response }) if startup.is_none() => {
                            let mut replies = read_replies.lock().unwrap();
                            if let Some(sender) = replies.pending.remove(&id) {
                                let _ = sender.send(response);
                            }
                        }
                        frame => {
                            let reason = frame.err().map(|e| e.to_string()).unwrap_or_default();
                            let _ = writeln!(log, "Invalid backend IPC frame: {reason}");
                            break;
                        }
                    }
                }
                let mut replies = read_replies.lock().unwrap();
                replies.closed = true;
                replies.pending.clear();
                let _ = writeln!(log, "Backend pipe closed. PID: {pid}");
            })
            .map_err(|err| log_error(err.to_string()))?;

        match startup.recv_timeout(Duration::from_secs(45)) {
            Ok(()) => Ok(backend),
            Err(err) => {
                let exit = backend
                    .child
                    .lock()
                    .unwrap()
                    .as_mut()
                    .and_then(|child| child.try_wait().ok().flatten());
                let message = if chinese {
                    "后台启动失败"
                } else {
                    "Backend startup failed"
                };
                let detail = exit.map_or_else(|| err.to_string(), |status| status.to_string());
                let report = log_error(format!("{message} ({detail})"));
                if let Ok(mut log) = OpenOptions::new().append(true).open(&log_path) {
                    let _ = writeln!(log, "{report}");
                }
                Err(report)
            }
        }
    }

    pub async fn request(&self, target: String, body: Option<String>) -> Result<Response, String> {
        if !target.starts_with("/api/") || target.contains(['\r', '\n', '#']) || target.len() > 8192
        {
            return Err(self.text("请求路径无效", "Invalid API path").into());
        }
        if body.as_ref().is_some_and(|body| body.len() > 8_000_000) {
            return Err(self.text("请求大小无效", "Invalid request size").into());
        }
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        let (sender, receiver) = oneshot::channel();
        {
            let mut replies = self.replies.lock().unwrap();
            if replies.closed {
                return Err(self.disconnected());
            }
            if replies.pending.len() >= MAX_PENDING {
                return Err(self
                    .text(
                        "后台请求过多，请稍后重试。",
                        "Backend is busy. Try again shortly.",
                    )
                    .into());
            }
            replies.pending.insert(id, sender);
        }
        let mut pending = Pending {
            id,
            replies: Arc::clone(&self.replies),
        };
        let frame = Request {
            id,
            method: if body.is_some() { "POST" } else { "GET" },
            target: &target,
            body: body.as_deref(),
        };
        let mut encoded = serde_json::to_vec(&frame).map_err(|err| err.to_string())?;
        encoded.push(b'\n');
        if encoded.len() > MAX_FRAME {
            return Err(self.text("请求大小无效", "Invalid request size").into());
        }
        let input = Arc::clone(&self.input);
        let sent = tauri::async_runtime::spawn_blocking(move || {
            input
                .lock()
                .unwrap()
                .as_mut()
                .is_some_and(|pipe| pipe.write_all(&encoded).is_ok())
        })
        .await;
        if !matches!(sent, Ok(true)) {
            return Err(self.disconnected());
        }
        let result = receiver.await.map_err(|_| self.disconnected());
        pending.id = 0;
        result
    }

    fn text<'a>(&self, chinese: &'a str, english: &'a str) -> &'a str {
        if self.chinese {
            chinese
        } else {
            english
        }
    }

    fn disconnected(&self) -> String {
        format!(
            "{}\n{}",
            self.text(
                "后台连接已断开，请重新打开工具。",
                "The backend disconnected. Reopen the app."
            ),
            self.log_path.display()
        )
    }

    pub fn stop(&self) {
        let child = self.child.lock().unwrap().take();
        if let Some(mut child) = child {
            // Terminating Python also closes its job object and reaps native match hosts.
            let _ = child.kill();
            let _ = child.wait();
        }
        self.input.lock().unwrap().take();
    }
}

impl Drop for Backend {
    fn drop(&mut self) {
        self.stop();
    }
}

struct Pending {
    id: u64,
    replies: Arc<Mutex<Replies>>,
}

impl Drop for Pending {
    fn drop(&mut self) {
        if self.id != 0 {
            self.replies.lock().unwrap().pending.remove(&self.id);
        }
    }
}
