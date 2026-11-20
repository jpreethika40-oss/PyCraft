"""Workspace management and file-reading/writing security tools for PyCraft.

This module provides restricted, sandboxed file listing, reading, and writing
operations constrained strictly to a configured workspace directory.
"""

import os
import tempfile
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

# Base directory paths
_APP_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _APP_DIR.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

# Explicitly load .env if present
if _ENV_FILE.exists():
    load_dotenv(dotenv_path=_ENV_FILE)
load_dotenv()

# Maximum allowed file size for reading and writing (100 KB)
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
    "api_key",
    "token",
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
        env_p = Path(env_path)
        root = env_p.resolve() if env_p.is_absolute() else (_PROJECT_ROOT / env_p).resolve()
    else:
        root = (_PROJECT_ROOT / "workspace").resolve()

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


def validate_and_resolve_path(
    rel_path_str: str,
    workspace_root: Optional[Path] = None,
    for_write: bool = False,
    for_delete: bool = False,
) -> Path:
    """
    Validate a workspace-relative path string and resolve it to an absolute Path.

    Safeguards:
    - Rejects empty paths.
    - Rejects null byte characters.
    - Rejects absolute paths (POSIX leading slash, UNC paths, Windows drive letters).
    - Rejects '..' directory traversal.
    - Rejects hidden and excluded files/directories.
    - Resolves symlinks and enforces strict workspace containment.
    - If for_write=False, for_delete=False: validates target exists and is a regular file.
    - If for_write=True: validates target directory/file stays inside workspace and is not an existing directory.
    - If for_delete=True: validates target exists, is a regular file, and is not excluded/sensitive.

    Raises:
        ValueError: For invalid path formats, traversals, or empty strings.
        PermissionError: If path escapes the workspace root boundary or targets excluded/sensitive files.
        FileNotFoundError: If the target does not exist (read/delete mode) or is excluded.
        IsADirectoryError: If the resolved path points to a directory.
    """
    if workspace_root is None:
        workspace_root = get_workspace_root()

    clean_str = rel_path_str.strip()
    if not clean_str:
        raise ValueError("File path cannot be empty.")

    if "\x00" in clean_str:
        raise ValueError("Path contains invalid null byte character.")

    # Reject absolute paths (POSIX leading slash, UNC paths, Windows drive letter)
    if clean_str.startswith(("/", "\\")) or (len(clean_str) >= 2 and clean_str[1] == ":"):
        raise ValueError("Absolute paths are not allowed. Please provide a workspace-relative path.")

    # Reject '..' traversal anywhere in the path parts (handling both / and \)
    normalized_str = clean_str.replace("\\", "/")
    raw_parts = [p for p in normalized_str.split("/") if p]
    if ".." in raw_parts or ".." in Path(clean_str).parts:
        raise ValueError("Path traversal ('..') is not permitted.")

    # Strip any '.' parts (current directory references)
    filtered_parts = [p for p in raw_parts if p != "."]
    if not filtered_parts:
        raise ValueError("File path cannot be empty.")

    # If the relative path redundantly starts with the workspace folder's name (e.g. "workspace/file.py"),
    # normalize it so writes and reads don't create or expect duplicate nested workspace directories
    resolved_root = workspace_root.resolve()
    if len(filtered_parts) > 1 and filtered_parts[0].lower() in ("workspace", resolved_root.name.lower()):
        filtered_parts = filtered_parts[1:]

    rel_path = Path(*filtered_parts)

    # Check for excluded path segments or filenames
    if is_path_excluded(rel_path):
        if for_write:
            raise PermissionError("Writing to excluded or sensitive paths is not permitted.")
        elif for_delete:
            raise PermissionError("Deleting excluded or sensitive paths is not permitted.")
        else:
            raise FileNotFoundError("The requested file is excluded or cannot be accessed.")

    # Construct the target path within the workspace
    target_path = workspace_root / rel_path

    # Canonicalize and resolve all symlinks
    resolved_root = workspace_root.resolve()
    try:
        resolved_path = target_path.resolve()
    except Exception as exc:
        raise ValueError(f"Could not resolve path: {exc}")

    # Enforce strict containment within the workspace (blocks symlink escapes)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        raise PermissionError("Access denied: path resolves outside the workspace boundary.")

    # Post-resolution containment check for excluded names (in case of symlink renaming)
    rel_resolved = resolved_path.relative_to(resolved_root)
    if is_path_excluded(rel_resolved):
        if for_write:
            raise PermissionError("Writing to excluded or sensitive paths is not permitted.")
        elif for_delete:
            raise PermissionError("Deleting excluded or sensitive paths is not permitted.")
        else:
            raise FileNotFoundError("The requested file is excluded or cannot be accessed.")

    if for_write:
        # For writing: target cannot be an existing directory
        if resolved_path.exists() and resolved_path.is_dir():
            raise IsADirectoryError(f"Path '{clean_str}' is a directory, not a regular file.")
    elif for_delete:
        # For deleting: target must exist and be a regular file
        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: '{clean_str}'")

        if resolved_path.is_dir():
            raise IsADirectoryError(f"Path '{clean_str}' is a directory, not a regular file.")

        if not resolved_path.is_file():
            raise ValueError(f"Path '{clean_str}' is not a regular file.")
    else:
        # For reading: target must exist and be a regular file
        if not resolved_path.exists():
            raise FileNotFoundError(f"File not found: '{clean_str}'")

        if resolved_path.is_dir():
            raise IsADirectoryError(f"Path '{clean_str}' is a directory, not a regular file.")

        if not resolved_path.is_file():
            raise ValueError(f"Path '{clean_str}' is not a regular file.")

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

    resolved_path = validate_and_resolve_path(rel_path_str, workspace_root, for_write=False)
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


def write_workspace_file(
    rel_path_str: str,
    content: str,
    overwrite: bool = False,
    workspace_root: Optional[Path] = None,
) -> tuple[str, str, int]:
    """
    Safely write UTF-8 text content to a file inside the configured workspace.

    Safeguards:
    - Strictly contained inside workspace root; traversal, absolute paths, and escapes are rejected.
    - Excluded files (.env, .git, virtualenvs, caches, credentials, secrets) cannot be written.
    - Only UTF-8 text is allowed, rejecting binary null bytes.
    - Content size capped at MAX_FILE_SIZE_BYTES (100 KB).
    - Existing files are protected from accidental overwrite unless overwrite=True.
    - Parent directories created automatically if needed inside workspace.
    - Uses atomic write (temp file + rename) to prevent partial or corrupted file writes.

    Args:
        rel_path_str: Workspace-relative path to the file.
        content: UTF-8 text content to save.
        overwrite: If True, replace existing file; if False, reject if already exists.
        workspace_root: Optional explicit workspace root path.

    Returns:
        Tuple of (clean_relative_path, operation, bytes_written)
        where operation is 'created' or 'updated'.

    Raises:
        FileExistsError: If file already exists and overwrite is False.
        PermissionError: If path resolves outside workspace or targets excluded/sensitive file.
        IsADirectoryError: If target path is a directory.
        ValueError: For invalid path, traversal, oversized content, or binary data.
    """
    if workspace_root is None:
        workspace_root = get_workspace_root()

    # 1. Content validation
    if not isinstance(content, str):
        raise ValueError("Content must be a valid text string.")

    if "\x00" in content:
        raise ValueError("Content contains binary null bytes and cannot be written as text.")

    try:
        encoded_bytes = content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("Content cannot be encoded as valid UTF-8 text.") from exc

    file_size = len(encoded_bytes)
    if file_size > MAX_FILE_SIZE_BYTES:
        max_kb = MAX_FILE_SIZE_BYTES // 1024
        file_kb = round(file_size / 1024, 1)
        raise ValueError(
            f"Content exceeds maximum allowed file size of {max_kb} KB ({file_kb} KB provided)."
        )

    # 2. Path validation and resolution (shares exact Phase 3 safeguards)
    resolved_path = validate_and_resolve_path(rel_path_str, workspace_root, for_write=True)
    resolved_root = workspace_root.resolve()
    rel_display_path = resolved_path.relative_to(resolved_root).as_posix()

    # 3. Check existing file state & overwrite permission
    if resolved_path.exists():
        if not overwrite:
            raise FileExistsError(
                f"File '{rel_display_path}' already exists and overwrite is set to false."
            )
        operation = "updated"
    else:
        operation = "created"

    # 4. Atomic write using temporary file in the same directory
    parent_dir = resolved_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    # Create atomic temp file in the target directory
    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=parent_dir,
        delete=False,
        prefix=f".tmp_{resolved_path.name}_",
    )
    temp_path = Path(temp_file.name)

    try:
        temp_file.write(content)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()

        # Atomic replacement of target file
        os.replace(temp_path, resolved_path)
    except Exception:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise

    return rel_display_path, operation, file_size


def delete_workspace_file(
    rel_path_str: str,
    workspace_root: Optional[Path] = None,
) -> tuple[str, bool]:
    """
    Safely delete a single regular file inside the configured workspace.

    Safeguards:
    - Strictly contained inside workspace root; traversal, absolute paths, and escapes are rejected.
    - Excluded and sensitive files (.env, .git, credentials, secrets) cannot be deleted.
    - Target must exist and be a regular file; directories cannot be deleted.
    - Deletes exactly one file; no bulk deletion or recycling.

    Args:
        rel_path_str: Workspace-relative path to the file to delete.
        workspace_root: Optional explicit workspace root path.

    Returns:
        Tuple of (clean_relative_path, True).

    Raises:
        FileNotFoundError: If the file does not exist.
        PermissionError: If path resolves outside workspace or targets excluded/sensitive file.
        IsADirectoryError: If target path is a directory.
        ValueError: For invalid path syntax, traversal, or non-regular files.
    """
    if workspace_root is None:
        workspace_root = get_workspace_root()

    resolved_path = validate_and_resolve_path(rel_path_str, workspace_root, for_delete=True)
    resolved_root = workspace_root.resolve()
    rel_display_path = resolved_path.relative_to(resolved_root).as_posix()

    try:
        resolved_path.unlink()
    except OSError as exc:
        raise ValueError(f"Failed to delete file '{rel_display_path}': {exc}") from exc

    return rel_display_path, True

