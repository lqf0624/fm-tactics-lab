#![windows_subsystem = "windows"]

mod backend;
mod data_directory;
mod install;

use backend::{Backend, Response};
use base64::{engine::general_purpose::STANDARD, Engine};
use std::ffi::OsString;
use std::fs;
use std::path::PathBuf;
use tauri::{Manager, RunEvent, State, WebviewWindow};
use tokio::sync::RwLock;
use windows_sys::Win32::Globalization::GetUserDefaultUILanguage;

const CHINESE_TITLE: &str = "FM27 战术实验室";
const ENGLISH_TITLE: &str = "FM27 Tactics Lab";
const EDITOR_ORIGIN: &str = "https://tauri.localhost";

struct Launch {
    data: PathBuf,
    settings: data_directory::Settings,
    override_data: bool,
    game: Option<PathBuf>,
    engine: Option<PathBuf>,
    self_test: bool,
    chinese: bool,
}

impl Launch {
    fn read() -> Result<Self, String> {
        let local = PathBuf::from(std::env::var_os("LOCALAPPDATA").ok_or("LOCALAPPDATA missing")?);
        let settings = data_directory::Settings::new(&local);
        let mut launch = Self {
            data: settings.default.clone(),
            settings,
            override_data: false,
            game: std::env::var_os("FM27_GAME_ROOT")
                .filter(|p| !p.is_empty())
                .map(PathBuf::from),
            engine: None,
            self_test: false,
            chinese: unsafe { GetUserDefaultUILanguage() } & 0x3ff == 4,
        };
        let mut args = std::env::args_os().skip(1);
        while let Some(argument) = args.next() {
            let option = argument.to_string_lossy();
            let mut next_path = || {
                args.next()
                    .filter(|value| !value.is_empty())
                    .map(PathBuf::from)
                    .ok_or_else(|| format!("Missing path for {option}"))
                    .and_then(|path| std::path::absolute(path).map_err(|err| err.to_string()))
            };
            match option.as_ref() {
                "--data-dir" => {
                    launch.data = next_path()?;
                    launch.override_data = true;
                }
                "--engine-root" => launch.engine = Some(next_path()?),
                "--game-root" => launch.game = Some(next_path()?),
                "--self-test" => launch.self_test = true,
                _ => return Err(format!("Unknown option: {option}")),
            }
        }
        Ok(launch)
    }

    fn choose_data(&mut self) -> Result<bool, Box<dyn std::error::Error>> {
        if self.override_data || self.self_test {
            return Ok(true);
        }
        let existing = self.settings.saved()?;
        if let Some(directory) = &existing {
            if directory.is_dir() {
                let default = data_directory::canonical(&self.settings.default)
                    .unwrap_or_else(|_| self.settings.default.clone());
                let selected = data_directory::canonical(directory)?;
                let idle = install::Instance::acquire(&selected, &default)?.is_some();
                if !idle
                    || (data_directory::check_writable(directory).is_ok()
                        && data_directory::check_capacity(directory, 0, self.chinese).is_ok())
                {
                    self.data = directory.clone();
                    return Ok(true);
                }
            }
        }
        let current = existing.as_ref().unwrap_or(&self.settings.default);
        let title = if existing.is_some() {
            self.text(
                "原数据目录无法使用，请重新选择",
                "The previous data folder is unavailable. Choose a new one.",
            )
        } else {
            self.text(
                "选择数据目录（取消则使用默认目录）",
                "Choose data folder (Cancel uses the default folder)",
            )
        };
        let mut dialog = rfd::FileDialog::new().set_title(title);
        if let Some(initial) = current.ancestors().find(|p| p.is_dir()) {
            dialog = dialog.set_directory(initial);
        }
        if let Some(path) = dialog.pick_folder() {
            let (target, destination) = data_directory::destination(&path)?;
            self.data = target;
            let source = data_directory::canonical(current).ok();
            if let Some(source) = source.filter(|p| !data_directory::same_path(p, &self.data)) {
                if data_directory::is_existing_workspace(&source)
                    && matches!(destination, data_directory::Destination::Empty)
                {
                    let choice = rfd::MessageDialog::new()
                    .set_title(self.title())
                    .set_description(self.text(
                        "是否把旧目录里的实验记录和存档缓存复制过来？选“否”直接使用所选目录。",
                        "Copy experiments and save caches from the old folder? Select No to use the selected folder as it is.",
                    ))
                    .set_buttons(rfd::MessageButtons::YesNoCancel)
                    .show();
                    match choice {
                        rfd::MessageDialogResult::Yes => {
                            if data_directory::overlaps(&source, &self.data) {
                                return Err(self.text(
                                    "请选择与原数据目录互不包含的文件夹。",
                                    "Choose a folder outside the old data folder and its parents.",
                                ).into());
                            }
                            let Some(_source_lock) =
                                install::Instance::acquire(&source, &self.settings.default)?
                            else {
                                return Err(self
                                    .text(
                                        "原数据目录正在被使用，请先退出旧窗口。",
                                        "Close the other window before copying its data.",
                                    )
                                    .into());
                            };
                            let Some(_target_lock) =
                                install::Instance::acquire(&self.data, &self.settings.default)?
                            else {
                                return Err(self
                                    .text(
                                        "所选目录正在被另一个窗口使用。",
                                        "Another window is using the selected folder.",
                                    )
                                    .into());
                            };
                            data_directory::copy_workspace(
                                &source,
                                &self.data,
                                Default::default(),
                                self.chinese,
                            )?;
                        }
                        rfd::MessageDialogResult::No => {}
                        _ => return Ok(false),
                    }
                }
            }
        } else if existing.is_some() {
            return Ok(false);
        }
        fs::create_dir_all(&self.data)?;
        data_directory::check_writable(&self.data)?;
        data_directory::check_capacity(&self.data, 0, self.chinese)?;
        self.settings.save(&self.data)?;
        Ok(true)
    }

    fn text<'a>(&self, chinese: &'a str, english: &'a str) -> &'a str {
        if self.chinese {
            chinese
        } else {
            english
        }
    }

    fn title(&self) -> &str {
        if self.chinese {
            CHINESE_TITLE
        } else {
            ENGLISH_TITLE
        }
    }
}

struct DataDirectory {
    active: PathBuf,
    settings: data_directory::Settings,
    chinese: bool,
    switching: RwLock<()>,
    moving: std::sync::atomic::AtomicBool,
}

impl DataDirectory {
    fn text<'a>(&self, chinese: &'a str, english: &'a str) -> &'a str {
        if self.chinese {
            chinese
        } else {
            english
        }
    }
}

#[tauri::command]
fn editor_data_directory(
    window: WebviewWindow,
    directory: State<'_, DataDirectory>,
) -> Result<PathBuf, String> {
    require_editor_window(&window)?;
    Ok(directory.active.clone())
}

#[tauri::command]
async fn editor_change_data_directory(
    window: WebviewWindow,
    directory: State<'_, DataDirectory>,
    backend: State<'_, Backend>,
    storage: data_directory::Workspace,
) -> Result<(), String> {
    require_editor_window(&window)?;
    let Some(selected) = rfd::AsyncFileDialog::new()
        .set_parent(&window)
        .set_title(directory.text("选择新的数据目录", "Choose a new data folder"))
        .set_directory(&directory.active)
        .pick_folder()
        .await
    else {
        return Ok(());
    };
    let (target, destination) =
        data_directory::destination(selected.path()).map_err(|err| err.to_string())?;
    if data_directory::same_path(&directory.active, &target) {
        return Ok(());
    }
    if data_directory::overlaps(&directory.active, &target) {
        return Err(directory
            .text(
                "请选择与当前数据目录互不包含的文件夹。",
                "Choose a folder outside the current data folder and its parents.",
            )
            .into());
    }
    let copy = matches!(destination, data_directory::Destination::Empty);
    let description = if copy {
        directory.text(
            "把实验记录、存档缓存和战术草稿复制到所选目录，完成后退出工具。再次打开时使用新目录。",
            "Copy experiments, save caches, and tactics drafts to the selected folder, then exit. Reopen the app to use the new folder.",
        )
    } else {
        directory.text(
            "所选目录已有工具数据。确认后退出工具，再次打开时使用该目录中的记录和草稿。",
            "This folder already contains app data. Confirm to exit and use that folder's experiments and drafts when you reopen.",
        )
    };
    if rfd::AsyncMessageDialog::new()
        .set_parent(&window)
        .set_title(directory.text("更改数据目录", "Change data folder"))
        .set_description(format!("{description}\n\n{}", target.display()))
        .set_buttons(rfd::MessageButtons::OkCancel)
        .show()
        .await
        != rfd::MessageDialogResult::Ok
    {
        return Ok(());
    }
    let busy = || {
        directory.text(
        "有操作正在进行，请等待比赛、读档或生成任务结束后再更改数据目录。",
        "Wait for matches, save reads, or tactic generation to finish before changing the data folder.",
    )
    };
    let _moving = Migration::begin(&directory).ok_or_else(|| busy().to_owned())?;
    let _switching = directory
        .switching
        .try_write()
        .map_err(|_| busy().to_owned())?;
    if !backend
        .request("/api/desktop-idle".into(), None)
        .await?
        .data["idle"]
        .as_bool()
        .unwrap_or(false)
    {
        return Err(busy().into());
    }
    let source = directory.active.clone();
    let settings = directory.settings.clone();
    let chinese = directory.chinese;
    tauri::async_runtime::spawn_blocking(move || -> Result<(), String> {
        let canonical_default = data_directory::canonical(&settings.default)
            .unwrap_or_else(|_| settings.default.clone());
        let Some(_target_lock) = install::Instance::acquire(&target, &canonical_default)
            .map_err(|err| err.to_string())?
        else {
            return Err(if chinese {
                "所选目录正在被另一个窗口使用。"
            } else {
                "Another window is using the selected folder."
            }
            .into());
        };
        if copy {
            data_directory::copy_workspace(&source, &target, storage, chinese)
                .map_err(|err| err.to_string())?;
        } else {
            data_directory::check_writable(&target).map_err(|err| err.to_string())?;
            data_directory::check_capacity(&target, 0, chinese).map_err(|err| err.to_string())?;
        }
        settings.save(&target).map_err(|err| err.to_string())
    })
    .await
    .map_err(|err| err.to_string())??;
    window.app_handle().exit(0);
    Ok(())
}

struct Migration<'a>(&'a DataDirectory);

impl<'a> Migration<'a> {
    fn begin(directory: &'a DataDirectory) -> Option<Self> {
        use std::sync::atomic::Ordering;
        directory
            .moving
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .ok()?;
        Some(Self(directory))
    }
}

impl Drop for Migration<'_> {
    fn drop(&mut self) {
        self.0
            .moving
            .store(false, std::sync::atomic::Ordering::Release);
    }
}

#[tauri::command]
async fn editor_request(
    window: WebviewWindow,
    backend: State<'_, Backend>,
    directory: State<'_, DataDirectory>,
    target: String,
    body: Option<String>,
) -> Result<Response, String> {
    require_editor_window(&window)?;
    let _request = directory.switching.read().await;
    if body.is_some() && matches!(target.as_str(), "/api/save/pick" | "/api/save/pick-folder") {
        let folder = target.ends_with("-folder");
        let chinese = unsafe { GetUserDefaultUILanguage() } & 0x3ff == 4;
        let mut dialog = rfd::AsyncFileDialog::new().set_parent(&window);
        let file = if folder {
            dialog = dialog.set_title(if chinese {
                "选择导出战术的文件夹"
            } else {
                "Choose tactics export folder"
            });
            dialog.pick_folder().await
        } else {
            dialog = dialog
                .set_title(if chinese {
                    "选择要读取的 FM27 存档"
                } else {
                    "Select an FM27 save"
                })
                .add_filter("Football Manager", &["fm", "fmf"])
                .add_filter(if chinese { "所有文件" } else { "All files" }, &["*"]);
            if let Some(home) = std::env::var_os("USERPROFILE").map(PathBuf::from) {
                let games = home.join("Documents/Sports Interactive/Football Manager 27/games");
                if games.is_dir() {
                    dialog = dialog.set_directory(games);
                }
            }
            dialog.pick_file().await
        };
        return Ok(Response {
            status: 200,
            data: serde_json::json!({"path": file.map(|file| file.path().to_path_buf())}),
        });
    }
    backend.request(target, body).await
}

#[tauri::command]
async fn editor_save_file(
    window: WebviewWindow,
    name: String,
    contents: String,
) -> Result<(), String> {
    require_editor_window(&window)?;
    if name.is_empty()
        || name
            .chars()
            .any(|c| c.is_control() || "\\/:*?\"<>|".contains(c))
    {
        return Err("Invalid export filename.".into());
    }
    let chinese = unsafe { GetUserDefaultUILanguage() } & 0x3ff == 4;
    let dialog = rfd::AsyncFileDialog::new()
        .set_parent(&window)
        .set_title(if chinese {
            "保存导出文件"
        } else {
            "Save export"
        })
        .set_file_name(name);
    let Some(file) = dialog.save_file().await else {
        return Ok(());
    };
    let bytes = STANDARD.decode(contents).map_err(|err| err.to_string())?;
    file.write(&bytes).await.map_err(|err| err.to_string())
}

fn require_editor_window(window: &WebviewWindow) -> Result<(), String> {
    let url = window.url().map_err(|err| err.to_string())?;
    if window.label() != "main" || url.origin().ascii_serialization() != EDITOR_ORIGIN {
        return Err("This command is only available in the main editor window.".into());
    }
    Ok(())
}

fn run(launch: &Launch) -> Result<(), Box<dyn std::error::Error>> {
    fs::create_dir_all(&launch.data)?;
    let data = data_directory::canonical(&launch.data)?;
    let default = data_directory::canonical(&launch.settings.default)
        .unwrap_or_else(|_| launch.settings.default.clone());
    let Some(_instance) = install::Instance::acquire(&data, &default)? else {
        return Err(if launch.chinese {
            "工具已在运行，请切换到现有窗口。"
        } else {
            "Switch to the running app window."
        }
        .into());
    };
    let release = install::unpack(&data)?;
    let engine = launch
        .engine
        .clone()
        .unwrap_or_else(|| release.join("engine"));
    let backend = Backend::start(
        &release,
        &engine,
        &data,
        launch.game.as_deref(),
        launch.chinese,
    )?;
    if launch.self_test {
        tauri::async_runtime::block_on(async {
            let status = backend.request("/api/status".into(), None).await?;
            let defaults = backend.request("/api/defaults".into(), None).await?;
            if status.data["engine"] != "original_native" || !defaults.data["teams"].is_array() {
                return Err("Unexpected backend startup response".to_owned());
            }
            fs::write(
                launch.data.join("self-test.json"),
                serde_json::to_vec_pretty(&serde_json::json!({
                    "ok": true, "transport": "stdio", "server_pid": backend.pid,
                    "engine": status.data["engine_compatibility"], "bundled_python": true
                }))
                .map_err(|err| err.to_string())?,
            )
            .map_err(|err| err.to_string())
        })?;
        return Ok(());
    }
    let title = launch.title().to_owned();
    let webview_data = data.join("webview");
    let script = data_directory::workspace_script(&data, EDITOR_ORIGIN)?;
    let directory = DataDirectory {
        active: data,
        settings: launch.settings.clone(),
        chinese: launch.chinese,
        switching: RwLock::new(()),
        moving: std::sync::atomic::AtomicBool::new(false),
    };
    let app = tauri::Builder::default()
        .manage(backend)
        .manage(directory)
        .invoke_handler(tauri::generate_handler![
            editor_request,
            editor_save_file,
            editor_data_directory,
            editor_change_data_directory
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window
                    .state::<DataDirectory>()
                    .moving
                    .load(std::sync::atomic::Ordering::Acquire)
                {
                    api.prevent_close();
                }
            }
        })
        .setup(move |app| {
            tauri::WebviewWindowBuilder::from_config(app, &app.config().app.windows[0])?
                .data_directory(webview_data)
                .initialization_script(script)
                .title(title)
                .on_navigation(|url| url.origin().ascii_serialization() == EDITOR_ORIGIN)
                .on_new_window(|_, _| tauri::webview::NewWindowResponse::Deny)
                .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())?;
    app.run(|app, event| {
        if let RunEvent::Exit = event {
            app.state::<Backend>().stop();
        }
    });
    Ok(())
}

fn main() {
    let mut launch = Launch::read();
    let outcome = match &mut launch {
        Ok(launch) => launch
            .choose_data()
            .and_then(|open| if open { run(launch) } else { Ok(()) }),
        Err(error) => Err(error.clone().into()),
    };
    if let Err(error) = outcome {
        let description = error.to_string();
        let (title, self_test) = match &launch {
            Ok(launch) => {
                let _ = fs::write(launch.data.join("tauri-startup-error.txt"), &description);
                (launch.title(), launch.self_test)
            }
            Err(_) => (
                ENGLISH_TITLE,
                std::env::args_os().any(|value| value == OsString::from("--self-test")),
            ),
        };
        if !self_test {
            rfd::MessageDialog::new()
                .set_title(title)
                .set_description(description)
                .set_level(rfd::MessageLevel::Error)
                .show();
        }
        std::process::exit(1);
    }
}
