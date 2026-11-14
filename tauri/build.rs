fn main() {
    println!("cargo:rerun-if-changed=../build/payload.zip");
    tauri_build::try_build(tauri_build::Attributes::new().windows_attributes(
        tauri_build::WindowsAttributes::new().window_icon_path("../assets/app-icon.ico"),
    ))
    .expect("could not build the FM27 desktop shell");
}
