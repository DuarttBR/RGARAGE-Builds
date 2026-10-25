"""Dependências comuns compiladas aqui a partir do código-fonte (nada de binário pronto de terceiros).
Instala em D:/rgbuild/deps/prefix (bin, include, lib, cmake) e guarda as licenças em D:/rgbuild/deps/licencas.

  python deps.py              compila o que faltar
  python deps.py sdl2 --force recompila uma dependência
"""
import os
import shutil
import subprocess
import sys

DEPS = r'D:\rgbuild\deps'
PREFIX = os.path.join(DEPS, 'prefix')
SRC = os.path.join(DEPS, 'src')
LIC = os.path.join(DEPS, 'licencas')
VCVARS = r'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
GEN = '-G "Visual Studio 17 2022" -A x64'

# nome: (repo, ref, submódulos, opções do cmake, arquivo que prova que já está instalado, licenças)
LIST = {
    'sdl2': ('libsdl-org/SDL', 'SDL2', False, '-DSDL_TEST=OFF', 'bin/SDL2.dll', ['LICENSE.txt']),
    'sdl3': ('libsdl-org/SDL', 'release-3.4.x', False, '-DSDL_TEST_LIBRARY=OFF -DSDL_TESTS=OFF -DSDL_EXAMPLES=OFF', 'bin/SDL3.dll', ['LICENSE.txt']),
    'sdl2_mixer': ('libsdl-org/SDL_mixer', 'SDL2', True, '-DSDL2MIXER_VENDORED=ON -DSDL2MIXER_SAMPLES=OFF -DSDL2MIXER_WAVPACK=OFF', 'bin/SDL2_mixer.dll', ['LICENSE.txt']),
    'sdl2_net': ('libsdl-org/SDL_net', 'SDL2', False, '-DSDL2NET_SAMPLES=OFF', 'bin/SDL2_net.dll', ['LICENSE.txt']),
    'zlib': ('madler/zlib', 'master', False, '-DZLIB_BUILD_EXAMPLES=OFF', 'bin/z.dll', ['LICENSE']),
    'libpng': ('pnggroup/libpng', 'libpng16', False, '-DPNG_TESTS=OFF -DPNG_TOOLS=OFF', 'bin/libpng16.dll', ['LICENSE']),
}


def run(cmd, cwd=None):
    print('$', cmd, flush=True)
    if subprocess.run(cmd, cwd=cwd, shell=True).returncode:
        raise SystemExit(f'falhou: {cmd}')


def build(name, force=False):
    repo, ref, subs, opts, proof, lics = LIST[name]
    if os.path.exists(os.path.join(PREFIX, proof)) and not force:
        print('já tem', name)
        return
    src = os.path.join(SRC, name)
    if os.path.exists(src):
        shutil.rmtree(src, onerror=lambda f, p, _: (os.chmod(p, 0o666), f(p)))
    run(f'git clone --depth 1 --branch {ref} {"--recurse-submodules --shallow-submodules" if subs else ""} https://github.com/{repo}.git "{src}"')
    pre = PREFIX.replace('\\', '/')
    run(f'call "{VCVARS}" >nul && cmake -S . -B build {GEN} -DCMAKE_INSTALL_PREFIX="{pre}" -DCMAKE_PREFIX_PATH="{pre}" {opts}', cwd=src)
    run(f'call "{VCVARS}" >nul && cmake --build build --config Release --parallel && cmake --install build --config Release', cwd=src)
    os.makedirs(os.path.join(LIC, name), exist_ok=True)
    for lf in lics:
        if os.path.exists(os.path.join(src, lf)):
            shutil.copy2(os.path.join(src, lf), os.path.join(LIC, name, f'{name.upper()}-{lf}'))
    sha = subprocess.run('git rev-parse HEAD', cwd=src, shell=True, capture_output=True, text=True).stdout.strip()
    open(os.path.join(LIC, name, f'{name.upper()}-ORIGEM.txt'), 'w', encoding='utf-8').write(f'https://github.com/{repo} ({ref}) commit {sha}\n')
    shutil.rmtree(os.path.join(src, 'build'), ignore_errors=True)
    print('ok', name)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    for n in (args or LIST):
        build(n, '--force' in sys.argv)
