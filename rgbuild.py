"""
RGARAGE-Builds: compila um port a partir da receita, empacota (binários + licença + créditos + código-fonte),
publica a release no GitHub e apaga a cópia local.

  python rgbuild.py receitas/ioquake3.json            compila, publica e limpa
  python rgbuild.py receitas/ioquake3.json --keep     não apaga a pasta de trabalho (para depurar a receita)
  python rgbuild.py receitas/ioquake3.json --no-publish
  python rgbuild.py receitas/ioquake3.json --reuse        usa a pasta de trabalho já compilada (pula clone e build)
Caminhos absolutos em collect/licenses valem (ex.: DLLs e licenças de D:/rgbuild/deps, as dependências compiladas aqui).

Receita (JSON):
  id, repo ("dono/nome"), ref (branch/tag, opcional), game, license, private (true = repositório privado),
  submodules (bool), steps ([comandos no cmd, com o ambiente do Visual Studio x64]),
  collect ([{"from": "pasta", "glob": "*.exe", "to": "subpasta opcional"}]), licenses (arquivos do projeto a incluir),
  needs (texto: o que o jogador precisa, ex. arquivos do jogo), needsEn (o mesmo em inglês: o hub mostra fora do português), exe (executável principal dentro do pacote),
  shell ("msys2" = passos no MSYS2 CLANG64 em vez do ambiente do Visual Studio), vcruntime (false = não copiar a runtime do VC++),
  crt ("x86" para builds de 32 bits), env (variáveis extras para os passos)
"""
import datetime
import glob
import json
import os
import shutil
import stat
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
WORK = r'D:\rgbuild\work'
OUT = r'D:\rgbuild\out'
VCVARS = r'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
MSYS2_ENV = r'C:\msys64\usr\bin\env.exe'
MSYS2_BASH = r'C:\msys64\usr\bin\bash.exe'
# arquivos de compilação que não vão para o pacote
SKIP = {'.exp', '.lib', '.pdb', '.ilk', '.iobj', '.ipdb', '.obj', '.tlog', '.lastbuildstate', '.recipe'}
REPOS = {False: ('DuarttBR/RGARAGE-Builds', r'D:\rgbuild\repos\RGARAGE-Builds'),
         True: ('DuarttBR/RGARAGE-Builds-Privado', r'D:\rgbuild\repos\RGARAGE-Builds-Privado')}


def run(cmd, cwd=None, env=None, check=True):
    print('$', cmd if isinstance(cmd, str) else ' '.join(cmd), flush=True)
    p = subprocess.run(cmd, cwd=cwd, env=env, shell=isinstance(cmd, str), stdin=subprocess.DEVNULL)
    if check and p.returncode != 0:
        raise SystemExit(f'falhou ({p.returncode}): {cmd}')
    return p.returncode


def out(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding='utf-8').stdout.strip()


def rmtree(p):
    def onerr(f, path, _):
        os.chmod(path, stat.S_IWRITE); f(path)
    if os.path.exists(p):
        shutil.rmtree(p, onerror=onerr)


def main():
    rec_path = sys.argv[1]
    keep = '--keep' in sys.argv
    publish = '--no-publish' not in sys.argv
    r = json.load(open(rec_path, encoding='utf-8'))
    rid, private = r['id'], bool(r.get('private'))
    slug_repo, local_repo = REPOS[private]
    src = os.path.join(WORK, rid)
    reuse = '--reuse' in sys.argv and os.path.isdir(os.path.join(src, '.git'))
    if not reuse:
        rmtree(src)
    os.makedirs(WORK, exist_ok=True); os.makedirs(OUT, exist_ok=True)

    # 1) código do autor
    clone = ['git'] + (['-c', 'core.autocrlf=false'] if r.get('lf') else []) + ['clone', '--depth', '1']   # lf: patches do autor exigem LF
    if r.get('ref'):
        clone += ['--branch', r['ref']]
    if r.get('submodules'):
        clone += ['--recurse-submodules', '--shallow-submodules']
    if not reuse:
        run(clone + [f'https://github.com/{r["repo"]}.git', src])
    sha = out(['git', 'rev-parse', 'HEAD'], cwd=src)
    date = datetime.date.today().strftime('%Y%m%d')
    tag = f'{rid}-{date}-{sha[:7]}'

    # 2) build com o ambiente do Visual Studio
    env = os.environ.copy()
    env.update(r.get('env', {}))
    if r.get('path'):   # pastas extras no começo do PATH (ex.: o bin do LLVM)
        env['PATH'] = os.pathsep.join(os.path.expandvars(p) for p in r['path']) + os.pathsep + env.get('PATH', '')
    for step in ([] if reuse else r['steps']):
        if r.get('shell') == 'msys2':
            # ports que só compilam com Clang/MinGW (ex.: os de PS4 baseados no bbport): MSYS2 CLANG64
            run([MSYS2_ENV, 'MSYSTEM=CLANG64', 'CHERE_INVOKING=1', MSYS2_BASH, '-lc', step], cwd=src, env=env)
        else:
            vc = os.path.join(os.path.dirname(VCVARS), r.get('vcvars', 'vcvars64.bat'))   # vcvars32.bat para builds de 32 bits
            run(f'call "{vc}" >nul && {step}', cwd=src, env=env)

    # 3) pacote
    stage = os.path.join(OUT, rid)
    rmtree(stage)
    os.makedirs(stage)
    n = 0
    for c in r['collect']:
        base = os.path.join(src, c['from'])
        for f in glob.glob(os.path.join(base, c.get('glob', '*')), recursive=True):
            rel = os.path.relpath(f, base)
            if os.path.splitext(f)[1].lower() in SKIP:
                continue
            dest = os.path.join(stage, c.get('to', ''), rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if os.path.isdir(f):
                shutil.copytree(f, dest, dirs_exist_ok=True, ignore=lambda d, names: [x for x in names if os.path.splitext(x)[1].lower() in SKIP])
            else:
                shutil.copy2(f, dest)
            n += 1
    if n == 0:
        raise SystemExit('nenhum arquivo coletado: confira "collect" na receita')
    # runtime do Visual C++ junto do exe (redistribuível da Microsoft; evita pedir o instalador do VC++ ao jogador)
    if r.get('vcruntime', True):
        crt = sorted(glob.glob(os.path.join(os.path.dirname(VCVARS), '..', '..', 'Redist', 'MSVC', '14.*', r.get('crt', 'x64'), 'Microsoft.VC143.CRT')))
        exe_dir = os.path.dirname(os.path.join(stage, r.get('exe', ''))) if r.get('exe') else stage
        for dll in ('vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'msvcp140_atomic_wait.dll', 'msvcp140_codecvt_ids.dll', 'concrt140.dll'):
            if crt and not os.path.exists(os.path.join(exe_dir, dll)) and os.path.exists(os.path.join(crt[-1], dll)):
                shutil.copy2(os.path.join(crt[-1], dll), exe_dir)
    lic_dir = os.path.join(stage, 'LICENCAS')
    os.makedirs(lic_dir, exist_ok=True)
    for lf in r.get('licenses', []):
        for f in glob.glob(os.path.join(src, lf)):
            if os.path.isdir(f):
                shutil.copytree(f, os.path.join(lic_dir, os.path.basename(f)), dirs_exist_ok=True)
            else:
                shutil.copy2(f, lic_dir)
    credits = f"""{r['game']} — build para Windows feito pelo RGARAGE HUB (não oficial)

Projeto original: https://github.com/{r['repo']}
Autores: os contribuidores do projeto acima (todo o crédito é deles).
Código usado: commit {sha} ({date[:4]}-{date[4:6]}-{date[6:]})
Licença: {r.get('license') or 'veja a pasta LICENCAS'}
{('O que você precisa: ' + r['needs']) if r.get('needs') else ''}
{('What you need: ' + r['needsEn']) if r.get('needsEn') else ''}

O código-fonte exato deste build está na release (fonte-{sha[:7]}.zip).
Nenhum arquivo de jogo vem neste pacote.
"""
    open(os.path.join(stage, 'CREDITOS.txt'), 'w', encoding='utf-8').write(credits)
    asset = os.path.join(OUT, f'{rid}-win64.zip')
    with zipfile.ZipFile(asset, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for d, _, fs in os.walk(stage):
            for f in fs:
                full = os.path.join(d, f)
                z.write(full, os.path.join(rid, os.path.relpath(full, stage)))
    source = os.path.join(OUT, f'fonte-{sha[:7]}.zip')
    run(['git', 'archive', '--format=zip', '-o', source, 'HEAD'], cwd=src)
    size = os.path.getsize(asset)
    print(f'pacote: {asset} ({size / 1e6:.1f} MB, {n} itens)')

    if not publish:
        print('sem publicar (--no-publish)')
        return

    # 4) release
    notes = f"""**{r['game']}** · build para Windows do projeto [{r['repo']}](https://github.com/{r['repo']}) (commit `{sha[:7]}`).

- Licença: {r.get('license') or 'veja LICENCAS'} · créditos e licença dentro do pacote; código-fonte exato em `fonte-{sha[:7]}.zip`.
{('- O que você precisa: ' + r['needs']) if r.get('needs') else ''}
{('- What you need: ' + r['needsEn']) if r.get('needsEn') else ''}
- Build não oficial feito pelo [RGARAGE HUB](https://github.com/DuarttBR/RGARAGE-HUB-Releases). Nenhum arquivo de jogo vem junto.

---
_English_: Windows build of [{r['repo']}](https://github.com/{r['repo']}) at `{sha[:7]}`. License and credits inside the package; exact source in `fonte-{sha[:7]}.zip`. Unofficial build by RGARAGE HUB; no game files included.
"""
    nf = os.path.join(OUT, f'{rid}-notas.md')
    open(nf, 'w', encoding='utf-8').write(notes)
    if run(['gh', 'release', 'view', tag, '--repo', slug_repo, '--json', 'tagName'], check=False) == 0:
        # mesmo commit no mesmo dia: atualiza os arquivos da release que já existe
        run(['gh', 'release', 'upload', tag, '--repo', slug_repo, '--clobber', asset, source])
        run(['gh', 'release', 'edit', tag, '--repo', slug_repo, '--notes-file', nf])
    else:
        run(['gh', 'release', 'create', tag, '--repo', slug_repo, '--title', f"{r['game']} · {rid} ({sha[:7]})", '--notes-file', nf, asset, source])

    # 5) receita e lista (o hub lê builds.json)
    rec_dest = os.path.join(local_repo, 'receitas', os.path.basename(rec_path))
    if os.path.abspath(rec_path) != os.path.abspath(rec_dest):
        shutil.copy2(rec_path, rec_dest)
    idx_path = os.path.join(local_repo, 'builds.json')
    idx = json.load(open(idx_path, encoding='utf-8'))
    idx['builds'] = [b for b in idx['builds'] if b['id'] != rid]
    idx['builds'].append({'id': rid, 'repo': r['repo'], 'game': r['game'], 'tag': tag, 'sha': sha, 'asset': os.path.basename(asset),
                          'size': size, 'license': r.get('license', ''), 'exe': r.get('exe', ''), 'needs': r.get('needs', ''), 'needsEn': r.get('needsEn', ''), 'date': date})
    idx['builds'].sort(key=lambda b: b['id'])
    json.dump(idx, open(idx_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    run(['git', 'add', '-A'], cwd=local_repo)
    if out(['git', 'status', '--porcelain'], cwd=local_repo):
        run(['git', 'commit', '-q', '-m', f"{r['game']}: build {tag}\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"], cwd=local_repo)
        run(['git', 'push', '-q', 'origin', 'main'], cwd=local_repo)

    # 6) limpa o PC: o build fica só no GitHub
    if not keep:
        rmtree(src)
    rmtree(stage)
    for f in (asset, source, nf):
        if os.path.exists(f):
            os.remove(f)
    print('ok', tag)


if __name__ == '__main__':
    main()
