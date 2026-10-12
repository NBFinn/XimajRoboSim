"""Private GitHub releases: existing CLI login or per-user DPAPI credential."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.parse
import urllib.request

_TOKEN = None

def credential_path():
    return Path(os.environ.get('APPDATA', str(Path.home()))) / 'XimajRoboSim' / 'github_access.dpapi'

class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

def crypt(data, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('Geschützter Zugangsspeicher ist unter Windows verfügbar.')
    buf = ctypes.create_string_buffer(data)
    src = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    dest = Blob()
    dll = ctypes.WinDLL('crypt32', use_last_error=True)
    fn = dll.CryptUnprotectData if decrypt else dll.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dest)):
        raise ctypes.WinError(ctypes.get_last_error())
    free = ctypes.WinDLL('kernel32').LocalFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(dest.data, dest.size)
    finally:
        free(dest.data)

def save_token(value):
    global _TOKEN
    value = value.strip()
    path = credential_path()
    if not value:
        path.unlink(missing_ok=True)
        _TOKEN = None
        return
    encrypted = crypt(value.encode())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypted)
    _TOKEN = value

def token():
    global _TOKEN
    if _TOKEN is not None:
        return _TOKEN
    try:
        _TOKEN = crypt(credential_path().read_bytes(), decrypt=True).decode()
        return _TOKEN
    except (OSError, RuntimeError, UnicodeError):
        pass
    gh = shutil.which('gh')
    if not gh:
        candidate = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'GitHub CLI' / 'gh.exe'
        gh = str(candidate) if candidate.is_file() else None
    if gh:
        try:
            result = subprocess.run([gh, 'auth', 'token', '--hostname', 'github.com'], capture_output=True,
                                    text=True, timeout=8, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode == 0:
                _TOKEN = result.stdout.strip()
                return _TOKEN
        except (OSError, subprocess.TimeoutExpired):
            pass
    return ''

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme != 'https':
            raise ValueError('Update-Weiterleitung muss HTTPS verwenden.')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlparse(req.full_url).hostname != urllib.parse.urlparse(newurl).hostname:
            redirected.remove_header('Authorization')
        return redirected

def get(url, repo, user_agent, timeout=15):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https':
        raise ValueError('Nur HTTPS erlaubt')
    is_repo_api = parsed.hostname == 'api.github.com' and parsed.path.startswith(f'/repos/{repo}/')
    accept = 'application/octet-stream' if is_repo_api and '/releases/assets/' in parsed.path else 'application/vnd.github+json'
    headers = {'User-Agent': user_agent, 'Accept': accept, 'X-GitHub-Api-Version': '2022-11-28'}
    if is_repo_api:
        access = token()
        if access:
            headers['Authorization'] = 'Bearer ' + access
    return urllib.request.build_opener(SafeRedirect()).open(urllib.request.Request(url, headers=headers), timeout=timeout)

def release_info(release, current, frozen=True):
    assets = release.get('assets', [])
    setups = [a for a in assets if a.get('name', '').lower().endswith('.exe') and 'setup' in a['name'].lower()]
    zips = [a for a in assets if a.get('name', '').lower().endswith('.zip')]
    chosen = (setups or zips) if frozen else (zips or setups)
    if not chosen:
        raise RuntimeError('Release enthält kein installierbares Setup oder ZIP.')
    asset = chosen[0]
    sha = next((a for a in assets if a.get('name') == asset['name'] + '.sha256'), None)
    if not sha:
        raise RuntimeError('Release enthält keine SHA-256-Datei.')
    return {'current': current, 'latest': release['tag_name'].lstrip('vV'), 'available': True,
            'name': asset['name'], 'url': asset.get('url') or asset['browser_download_url'],
            'sha_url': sha.get('url') or sha['browser_download_url'], 'size': asset.get('size', 0),
            'kind': 'setup' if asset in setups else 'zip', 'notes': release.get('body', '')}
