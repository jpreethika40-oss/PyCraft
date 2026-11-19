"""Workspace management and file-reading security tools for PyCraft.

This module provides restricted, read-only file listing and reading
operations constrained strictly to a configured workspace directory.
"""

import os
from pathlib import Path
from typing import List, Optional

# Maximum allowed file size for reading (100 KB)
MAX_FILE_SIZE_BYTES = 100 * 1024

# Files and directory names to exclude consistently
EXCLUDED_NAMES = {
    ".git",
    ".env",
    ".env.local",
    ".venv",
    "venv",
    "env",
    "ENV",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".coverage",
    ".idea",
    ".vscode",
    "node_modules",
}

# Binary and credential file extensions to exclude
EXCLUDED_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".pem",
    ".key",
    ".cer",
    ".crt",
    ".der",
    ".p12",
    ".pfx",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
}

# Patterns indicating potential credential or secret files
SENSITIVE_FILENAME_PATTERNS = {
    "id_rsa",
    "id_ed25519",
    "id_dsa",
    "credentials",
    "secrets",
    ".npmrc",
    ".dockercfg",
}


def get_workspace_root() -> Path:
    """
    Resolve and return the absolute canonical workspace path.
    Uses the PYCRAFT_WORKSPACE environment variable if set;
    otherwise defaults to the 'workspace/' directory in the project root.
    Creates the directory if it does not already exist.
    """
    env_path = os.getenv("PYCRAFT_WORKSPACE", "").strip()
    if env_path:
        root = Path(env_path).resolve()
    else:
        project_root = Path(__file__).resolve().parent.parent
        root = (project_root / "workspace").resolve()

    root.mkdir(parents=True, exist_ok=True)
    return root


def is_excluded_name(name: str) -> bool:
    """Check if a filename or directory name should be excluded."""
    lower_name = name.lower()

    # Hidden files or directories (starting with '.')
    if name.startswith("."):
        return True

    # Exact directory/file name exclusions
    if name in EXCLUDED_NAMES or lower_name in EXCLUDED_NAMES:
        return True

    # Sensitive credential filenames
    for pattern in SENSITIVE_FILENAME_PATTERNS:
        if pattern in lower_name:
            return True

    return False


def is_excluded_extension(path: Path) -> bool:
    """Check if a file has an excluded binary/credential extension."""
    suffix = path.suffix.lower()
    return suffix in EXCLUDED_EXTENSIONS


def is_path_excluded(rel_path: Path) -> bool:
    """Check if any segment of a relative path or the filename is excluded."""
    for part in rel_path.parts:
        if is_excluded_name(part):
            return True
    if is_excluded_extension(rel_path):
        return True
    return False


def validate_and_resolve_path(rel_path_str: str, workspace_root: Optional[Path] = None) -> Path:
    """
    Validate a workspace-relative path string and resolve it to an absolute Path.

    Safeguards:
    - Rejects empty paths.
    - Rejects absolute paths (Windows drive letters, UNC, leading slashes).
    - Rejects '..' directory traversal.
    - Rejects hidden and excluded files/directories.
    - Resolves symlinks and enforces strict workspace containment.
    - Validates target exists and is a regular file.

    Raises:
        ValueError: For invalid path formats, traversals, or exclusions.
        PermissionError: If path escapes the workspace root boundary.
        FileNotFoundError: If the target does not exist or is excluded.
        IsADirectoryError: If the resolved path points to a directory.
    """
    if workspace_root is None:
        workspace_root = get_workspace_root()

    clean_str = rel_path_str.strip()
    if not clean_str:
        raise ValueError("File path cannot be empty.")

    # Reject absolute paths (POSIX leading slash or Windows drive letter)
    if clean_str.startswith(("/", "\\")) or (len(clean_str) >= 2 and clean_str[1] == ":"):
        raise ValueError("Absolute paths are not allowed. Please provide a workspace-relative path.")

    rel_path = Path(clean_str)

    # Reject '..' traversal anywhere in the path parts
    if ".." in rel_path.parts:
        raise ValueError("Path traversal ('..') is not permitted.")

    # Check for excluded path segments or filenames
    if is_path_excluded(rel_path):
        raise FileNotFoundError("The requested file is excluded or cannot be accessed.")

    # Construct the target path within the workspace
    target_path = workspace_root / rel_path

    # Canonicalize and resolve all symlinks
    resolved_root = workspace_root.resolve()
    try:
        resolved_path = target_path.resolve()
    except Exception as exc:
        raise ValueError(f"Could not resolve path: {exc}")

    # Enforce strict containment within the workspace
    try:
        # Raises ValueError if resolved_path is not within resolved_root
        resolved_path.relative_to(resolved_root)
    except ValueError:
        raise PermissionError("Access denied: path resolves outside the workspace boundary.")

    # Check existence
    if not resolved_path.exists():
        raise FileNotFoundError(f"File not found: '{clean_str}'")

    # Reject directories
    if resolved_path.is_dir():
        raise IsADirectoryError(f"Path '{clean_str}' is a directory, not a regular file.")

    # Ensure the resolved target is a regular file
    if not resolved_path.is_file():
        raise ValueError(f"Path '{clean_str}' is not a regular file.")

    # Post-resolution containment check for excluded names (in case of symlink renaming)
    rel_resolved = resolved_path.relative_to(resolved_root)
    if is_path_excluded(rel_resolved):
        raise FileNotFoundError("The requested file is excluded or cannot be accessed.")

    return resolved_path


def list_workspace_files(workspace_root: Optional[Path] = None) -> List[str]:
    """
    List all accessible, non-excluded files inside the workspace.

    Returns:
        List of relative paths (using forward slashes) sorted alphabetically.
    """
    if workspace_root is None:
        workspace_root = get_workspace_root()

    resolved_root = workspace_root.resolve()
    discovered_files: List[str] = []

    for root, dirs, files in os.walk(resolved_root):
        current_dir = Path(root)

        # Prune excluded directories in-place so os.walk does not descend into them
        dirs[:] = [
            d for d in dirs
            if not is_excluded_name(d)
            and not (current_dir / d).is_symlink()
        ]

        for file_name in files:
            if is_excluded_name(file_name):
                continue

            file_path = current_dir / file_name

            # Skip symlinks that escape workspace
            try:
                resolved_file = file_path.resolve()
                resolved_file.relative_to(resolved_root)
            except (ValueError, RuntimeError):
                continue

            if not resolved_file.is_file():
                continue

            if is_excluded_extension(resolved_file):
                continue

            # Check file size limitation
            try:
                if resolved_file.stat().st_size > MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue

            # Compute relative path with forward slashes for clean portable responses
            rel_path = resolved_file.relative_to(resolved_root).as_posix()
            discovered_files.append(rel_path)

    discovered_files.sort()
    return discovered_files


def read_workspace_file(rel_path_str: str, workspace_root: Optional[Path] = None) -> tuple[str, str, int]:
    """
    Read and return the contents of a UTF-8 text file in the workspace.

    Args:
        rel_path_str: Workspace-relative path to the file.
        workspace_root: Optional explicit workspace root path.

    Returns:
        Tuple of (clean_relative_path, text_content, file_size_in_bytes).

    Raises:
        ValueError: For traversal, exclusion, oversize, or non-UTF8/binary content.
        PermissionError: For containment violations.
        FileNotFoundError: For missing files.
        IsADirectoryError: For directory paths.
    """
    if workspace_root is None:
        workspace_root = get_workspace_root()

    resolved_path = validate_and_resolve_path(rel_path_str, workspace_root)
    resolved_root = workspace_root.resolve()
    rel_display_path = resolved_path.relative_to(resolved_root).as_posix()

    # Size check
    file_size = resolved_path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        max_kb = MAX_FILE_SIZE_BYTES // 1024
        file_kb = round(file_size / 1024, 1)
        raise ValueError(
            f"File exceeds maximum allowed size of {max_kb} KB (file is {file_kb} KB)."
        )

    # Read binary bytes first to detect null bytes and UTF-8 encoding
    raw_bytes = resolved_path.read_bytes()

    # Check for binary null byte indicator
    if b"\x00" in raw_bytes:
        raise ValueError("File contains binary data and cannot be read as text.")

    # UTF-8 decoding
    try:
        content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("File is not a valid UTF-8 text file.") from exc

    return rel_display_path, content, file_size

