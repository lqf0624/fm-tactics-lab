use sha2::{Digest, Sha256};
use std::ffi::OsStr;
use std::fs::{self, File};
use std::io::{self, Cursor};
use std::os::windows::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::ptr;
use windows_sys::Win32::Foundation::{CloseHandle, GetLastError, ERROR_ALREADY_EXISTS, HANDLE};
use windows_sys::Win32::Storage::FileSystem::GetDiskFreeSpaceExW;
use windows_sys::Win32::System::Threading::CreateMutexW;
use zip::ZipArchive;

static PAYLOAD: &[u8] = include_bytes!("../../build/payload.zip");

fn release_path(data: &Path, hash: &str) -> PathBuf {
    data.join("releases").join(format!("tauri-{}", &hash[..20]))
}

pub fn required_bytes(data: &Path) -> io::Result<u64> {
    let hash = format!("{:x}", Sha256::digest(PAYLOAD));
    if release_path(data, &hash).join(".ready").is_file() {
        return Ok(0);
    }
    payload_bytes()
}

fn payload_bytes() -> io::Result<u64> {
    let mut archive = ZipArchive::new(Cursor::new(PAYLOAD))?;
    let mut bytes = 0u64;
    for index in 0..archive.len() {
        bytes = bytes.saturating_add(archive.by_index(index)?.size());
    }
    Ok(bytes)
}

pub struct Instance(HANDLE);

impl Instance {
    pub fn acquire(data: &Path, default_data: &Path) -> io::Result<Option<Self>> {
        let name = if data == default_data {
            "Local\\FM27TacticsDesktop_Editor".to_owned()
        } else {
            let id = Sha256::digest(data.to_string_lossy().to_lowercase().as_bytes());
            format!("Local\\FM27TacticsDesktop_Editor_{id:x}")
        };
        let mutex = unsafe { CreateMutexW(ptr::null(), 0, wide(OsStr::new(&name)).as_ptr()) };
        if mutex.is_null() {
            return Err(io::Error::last_os_error());
        }
        let instance = Self(mutex);
        if unsafe { GetLastError() } == ERROR_ALREADY_EXISTS {
            return Ok(None);
        }
        Ok(Some(instance))
    }
}

impl Drop for Instance {
    fn drop(&mut self) {
        unsafe { CloseHandle(self.0) };
    }
}

fn wide(value: &OsStr) -> Vec<u16> {
    value.encode_wide().chain(std::iter::once(0)).collect()
}

pub fn free_bytes(directory: &Path) -> io::Result<u64> {
    let mut free = 0;
    if unsafe {
        GetDiskFreeSpaceExW(
            wide(directory.as_os_str()).as_ptr(),
            &mut free,
            ptr::null_mut(),
            ptr::null_mut(),
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok(free)
}

pub fn unpack(data: &Path) -> Result<PathBuf, Box<dyn std::error::Error>> {
    let hash = format!("{:x}", Sha256::digest(PAYLOAD));
    let releases = data.join("releases");
    let release = release_path(data, &hash);
    if release.join(".ready").is_file() {
        return Ok(release);
    }
    fs::create_dir_all(&releases)?;
    let required = payload_bytes()?;
    let free = free_bytes(&releases)?;
    if free < required {
        return Err(io::Error::other(format!(
            "Not enough free disk space ({} MiB required)\n{}",
            required.div_ceil(1024 * 1024),
            releases.display()
        ))
        .into());
    }
    let staging = tempfile::Builder::new()
        .prefix(".tauri-install-")
        .tempdir_in(&releases)?;
    let mut archive = ZipArchive::new(Cursor::new(PAYLOAD))?;
    for index in 0..archive.len() {
        let mut entry = archive.by_index(index)?;
        let relative = entry
            .enclosed_name()
            .ok_or("invalid desktop payload path")?;
        let path = staging.path().join(relative);
        if entry.is_dir() {
            fs::create_dir_all(path)?;
        } else {
            fs::create_dir_all(path.parent().ok_or("invalid payload parent")?)?;
            io::copy(&mut entry, &mut File::create(path)?)?;
        }
    }
    fs::write(staging.path().join(".ready"), hash)?;
    fs::rename(staging.path(), &release)?;
    Ok(release)
}
