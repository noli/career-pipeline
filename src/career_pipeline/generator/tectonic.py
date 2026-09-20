"""
career_pipeline.generator.tectonic - Headless LaTeX Compiler
Uses shutil.which to ensure seamless cross-platform execution on Windows, macOS, and Linux.
"""
import shutil
import subprocess
from pathlib import Path

def is_tectonic_installed() -> bool:
    return shutil.which("tectonic") is not None

def compile_tex_to_pdf(tex_path: Path, output_dir: Path, verbose: bool = False) -> bool:
    """Compiles a LaTeX file into PDF using local headless Tectonic."""
    if not is_tectonic_installed():
        if verbose:
            print("Warning: 'tectonic' is not installed on PATH. Skipping automated PDF generation.")
        return False

    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["tectonic", str(tex_path), "--outdir", str(output_dir)]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        if verbose:
            print(f"Compiled PDF successfully: {output_dir / (tex_path.stem + '.pdf')}")
        return True
    except subprocess.CalledProcessError as e:
        if verbose:
            print(f"Error compiling {tex_path.name} with tectonic: {e.stderr}")
        return False
