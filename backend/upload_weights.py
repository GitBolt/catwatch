import modal

app = modal.App("dronecat-upload")
vol = modal.Volume.from_name("dronecat-models", create_if_missing=True)

image = modal.Image.debian_slim(python_version="3.11")

@app.function(image=image, volumes={"/models": vol})
def upload():
    import subprocess
    subprocess.run(["ls", "-lh", "/models"], check=True)

@app.local_entrypoint()
def main():
    import pathlib

    local_path = pathlib.Path(__file__).parent / "modal_app" / "weights" / "dronecat_yolo_best.pt"
    if not local_path.exists():
        print(f"File not found: {local_path}")
        return

    size_mb = local_path.stat().st_size / (1024 * 1024)
    print(f"Uploading {local_path.name} ({size_mb:.1f} MB)...")

    vol = modal.Volume.from_name("dronecat-models", create_if_missing=True)
    with vol.batch_upload(force=True) as batch:
        batch.put_file(str(local_path), "dronecat_yolo_best.pt")

    print("Done. Verifying...")
    upload.remote()
