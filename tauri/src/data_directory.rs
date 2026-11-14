use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs::{self, File};
use std::io::{self, Write};
use std::os::windows::fs::MetadataExt;
use std::path::{Path, PathBuf};
use windows_sys::Win32::Storage::FileSystem::FILE_ATTRIBUTE_REPARSE_POINT;

const APP_NAME: &str = "FM27TacticsDesktop";
const SNAPSHOT: &str = "tactics-workspace.json";
const STORED_DATA: &[&str] = &[
    "runs",
    "save_library",
    "game_db_names",
    "preset_plans",
    "exports",
    "imports",
    "logs",
    "game-root.txt",
    "native-source-plan.key",
];
pub type Workspace = BTreeMap<String, String>;

#[derive(Clone)]
pub struct Settings {
    pub default: PathBuf,
    config: PathBuf,
}

#[derive(Deserialize, Serialize)]
struct Location {
    data_directory: PathBuf,
}

#[derive(Serialize, Deserialize)]
struct Snapshot {
    storage: Workspace,
}

impl Settings {
    pub fn new(local_app_data: &Path) -> Self {
        Self {
            default: local_app_data.join(APP_NAME),
            config: local_app_data.join(format!("{APP_NAME}.settings.json")),
        }
    }

    pub fn saved(&self) -> io::Result<Option<PathBuf>> {
        match File::open(&self.config) {
            Ok(file) => {
                let location: Location = serde_json::from_reader(file)?;
                if !location.data_directory.is_absolute() {
                    return Err(io::Error::other("Invalid saved data directory"));
                }
                Ok(Some(location.data_directory))
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
            Err(error) => Err(error),
        }
    }

    pub fn save(&self, directory: &Path) -> io::Result<()> {
        let parent = self.config.parent().expect("settings parent");
        fs::create_dir_all(parent)?;
        let mut staging = tempfile::NamedTempFile::new_in(parent)?;
        serde_json::to_writer(
            &mut staging,
            &Location {
                data_directory: directory.to_owned(),
            },
        )?;
        staging.flush()?;
        staging.as_file().sync_all()?;
        staging.persist(&self.config)?;
        Ok(())
    }
}

pub fn canonical(directory: &Path) -> io::Result<PathBuf> {
    let path = fs::canonicalize(directory)?;
    let text = path.to_string_lossy();
    // Keep ordinary drive and UNC paths compatible with WebView2 and the native engine.
    if let Some(share) = text.strip_prefix(r"\\?\UNC\") {
        return Ok(PathBuf::from(format!(r"\\{share}")));
    }
    if let Some(drive) = text.strip_prefix(r"\\?\") {
        if drive.as_bytes().get(1) == Some(&b':') {
            return Ok(PathBuf::from(drive));
        }
    }
    Ok(path)
}

pub fn is_existing_workspace(directory: &Path) -> bool {
    directory.join("runs").is_dir() && directory.join("save_library").is_dir()
}

#[derive(PartialEq, Eq)]
pub enum Destination {
    Empty,
    Existing,
}

fn classify(directory: &Path) -> io::Result<Option<Destination>> {
    if is_existing_workspace(directory) {
        return Ok(Some(Destination::Existing));
    }
    match fs::read_dir(directory) {
        Ok(mut entries) => Ok(entries
            .next()
            .transpose()?
            .is_none()
            .then_some(Destination::Empty)),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(Some(Destination::Empty)),
        Err(error) if error.kind() == io::ErrorKind::NotADirectory => Ok(None),
        Err(error) => Err(error),
    }
}

pub fn destination(selected: &Path) -> io::Result<(PathBuf, Destination)> {
    let selected = canonical(selected)?;
    if selected.parent().is_some() {
        if let Some(kind) = classify(&selected)? {
            return Ok((selected, kind));
        }
    }
    for number in 1.. {
        let name = if number == 1 {
            APP_NAME.to_owned()
        } else {
            format!("{APP_NAME}-{number}")
        };
        let directory = selected.join(name);
        match fs::symlink_metadata(&directory) {
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                return Ok((directory, Destination::Empty))
            }
            Err(error) => return Err(error),
            Ok(metadata)
                if metadata.is_dir()
                    && metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT == 0 =>
            {
                if let Some(kind) = classify(&directory)? {
                    return Ok((canonical(&directory)?, kind));
                }
            }
            _ => {}
        }
    }
    unreachable!()
}

pub fn check_writable(directory: &Path) -> io::Result<()> {
    tempfile::NamedTempFile::new_in(directory)?.close()
}

pub fn check_capacity(directory: &Path, extra: u64, chinese: bool) -> io::Result<()> {
    let required = super::install::required_bytes(directory)?.saturating_add(extra);
    if super::install::free_bytes(directory)? < required {
        let mib = required.div_ceil(1024 * 1024);
        return Err(io::Error::other(if chinese {
            format!("所选目录可用空间不足，本次需要 {mib} MiB。")
        } else {
            format!("The selected folder needs {mib} MiB of free space.")
        }));
    }
    Ok(())
}

pub fn same_path(first: &Path, second: &Path) -> bool {
    first.to_string_lossy().to_lowercase() == second.to_string_lossy().to_lowercase()
}

pub fn overlaps(first: &Path, second: &Path) -> bool {
    let first = PathBuf::from(first.to_string_lossy().to_lowercase());
    let second = PathBuf::from(second.to_string_lossy().to_lowercase());
    first.starts_with(&second) || second.starts_with(&first)
}

fn collect_files(root: &Path, relative: &Path, files: &mut Vec<(PathBuf, u64)>) -> io::Result<()> {
    let absolute = root.join(relative);
    let metadata = fs::symlink_metadata(&absolute)?;
    if metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0 {
        return Err(io::Error::other(format!(
            "Cannot copy a linked entry: {}",
            absolute.display()
        )));
    }
    if metadata.is_dir() {
        for entry in fs::read_dir(absolute)? {
            collect_files(root, &relative.join(entry?.file_name()), files)?;
        }
    } else if metadata.is_file() {
        files.push((relative.to_owned(), metadata.len()));
    }
    Ok(())
}

pub fn copy_workspace(
    source: &Path,
    target: &Path,
    mut storage: Workspace,
    chinese: bool,
) -> io::Result<()> {
    if classify(target)? != Some(Destination::Empty) {
        return Err(io::Error::other(if chinese {
            "所选目录已有数据，请重新选择。"
        } else {
            "The destination already contains data. Choose a folder again."
        }));
    }
    storage.retain(|key, _| key.starts_with("fm27-") && key != "fm27-directory-migrated");
    let snapshot = serde_json::to_vec(&Snapshot { storage })?;
    let mut files = Vec::new();
    for name in STORED_DATA {
        match fs::symlink_metadata(source.join(name)) {
            Ok(_) => collect_files(source, Path::new(name), &mut files)?,
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(error),
        }
    }
    let bytes = files
        .iter()
        .fold(snapshot.len() as u64, |total, (_, size)| {
            total.saturating_add(*size)
        });
    let parent = target.parent().expect("validated destination");
    check_capacity(parent, bytes, chinese)?;
    let staging = tempfile::Builder::new()
        .prefix(".fm27-copy-")
        .tempdir_in(parent)?;
    for (relative, _) in files {
        let path = staging.path().join(&relative);
        fs::create_dir_all(path.parent().expect("file parent"))?;
        fs::copy(source.join(relative), path)?;
    }
    fs::create_dir_all(staging.path().join("runs"))?;
    fs::create_dir_all(staging.path().join("save_library"))?;
    fs::write(staging.path().join(SNAPSHOT), snapshot)?;
    // Removing an empty folder fails if anything has appeared in it since selection.
    let existed = match fs::remove_dir(target) {
        Ok(()) => true,
        Err(error) if error.kind() == io::ErrorKind::NotFound => false,
        Err(error) => return Err(error),
    };
    if let Err(error) = fs::rename(staging.path(), target) {
        if existed {
            let _ = fs::create_dir(target);
        }
        return Err(error);
    }
    Ok(())
}

pub fn workspace_script(directory: &Path, origin: &str) -> io::Result<String> {
    let snapshot = directory.join(SNAPSHOT);
    let file = match File::open(snapshot) {
        Ok(file) => file,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(String::new()),
        Err(error) => return Err(error),
    };
    let Snapshot { storage } = serde_json::from_reader(file)?;
    let origin = serde_json::to_string(origin)?;
    let storage = serde_json::to_string(&storage)?;
    Ok(format!(
        r#"
        if (location.origin === {origin} && !localStorage.getItem('fm27-directory-migrated')) {{
            for (const [key, value] of Object.entries({storage})) {{
                if (localStorage.getItem(key) === null) localStorage.setItem(key, value);
            }}
            localStorage.setItem('fm27-directory-migrated', '1');
        }}
    "#
    ))
}
