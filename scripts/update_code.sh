#!/usr/bin/env bash
# update_code.sh - Terapkan versi kode terbaru ke repo lokal, uji, commit, dan deploy.
#
# Cara pakai:
#   1. Ekstrak pln-scada-sim.zip terbaru ke folder SEMENTARA (bukan ke repo-mu).
#   2. Dari folder hasil ekstrak itu, jalankan:
#        bash scripts/update_code.sh --repo /path/ke/repo-kamu --dry-run     # lihat perubahan saja
#        bash scripts/update_code.sh --repo /path/ke/repo-kamu --deploy up   # terapkan + deploy via CLI
#
# Yang dikerjakan: salin berkas kode yang berubah (tanpa menghapus apa pun di repo-mu),
# jalankan smoke test, commit, lalu deploy. Folder data/ tidak disentuh kecuali --with-data.
#
# Opsi:
#   --repo PATH      repo lokal yang akan diperbarui (wajib)
#   --source PATH    folder kode terbaru (default: folder induk skrip ini)
#   --deploy MODE    push (git push, default) | up (railway up) | none
#   --service NAMA   service Railway untuk mode up (default: pln-scada-sim)
#   --url URL        alamat API untuk memeriksa deploy (default: variabel BASE atau alamat produksi)
#   --message TEKS   pesan commit
#   --with-data      ikut menyalin folder data/
#   --skip-tests     lewati smoke test (tidak disarankan)
#   --force          lanjut walau ada perubahan belum di-commit pada berkas yang sudah terlacak
#   --dry-run        hanya tampilkan daftar perubahan
#   --yes            lewati pertanyaan konfirmasi
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO=""
DEPLOY="push"
SERVICE="pln-scada-sim"
BASE="${BASE:-https://pln-scada-sim-production.up.railway.app}"
MSG="Perbarui kode: parsing API_KEYS ketat, /health menampilkan jumlah key, endpoint /kb, skrip operasi"
WITH_DATA=0; SKIP_TESTS=0; FORCE=0; DRY=0; YES=0
WAIT_MAX="${WAIT_MAX:-300}"
POLL="${POLL_INTERVAL:-10}"

usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --repo)       REPO="${2:?}"; shift 2 ;;
    --source)     SOURCE="$(cd "${2:?}" && pwd)"; shift 2 ;;
    --deploy)     DEPLOY="${2:?}"; shift 2 ;;
    --service)    SERVICE="${2:?}"; shift 2 ;;
    --url)        BASE="${2:?}"; shift 2 ;;
    --message)    MSG="${2:?}"; shift 2 ;;
    --with-data)  WITH_DATA=1; shift ;;
    --skip-tests) SKIP_TESTS=1; shift ;;
    --force)      FORCE=1; shift ;;
    --dry-run)    DRY=1; shift ;;
    --yes|-y)     YES=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "Opsi tidak dikenal: $1" >&2; usage >&2; exit 2 ;;
  esac
done
BASE="${BASE%/}"

say() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
confirm() {  # $1 = pertanyaan
  [ "$YES" -eq 1 ] && return 0
  printf '%s [y/N] ' "$1"; read -r a
  case "$a" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

# ---------------------------------------------------------------- validasi
[ -n "$REPO" ] || { usage >&2; die "--repo wajib diisi"; }
[ -d "$REPO" ] || die "Folder repo tidak ditemukan: $REPO"
REPO="$(cd "$REPO" && pwd)"
[ "$REPO" != "$SOURCE" ] || die "Folder sumber dan repo sama ($REPO). Ekstrak zip ke folder lain."
[ -f "$SOURCE/app/main.py" ] && [ -f "$SOURCE/simcore/store.py" ] || die "Folder sumber bukan paket pln-scada-sim: $SOURCE"
git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "$REPO bukan repo git"
[ -f "$REPO/app/main.py" ] || die "$REPO tidak berisi app/main.py; apakah ini repo yang benar?"
case "$DEPLOY" in push|up|none) ;; *) die "--deploy harus push, up, atau none" ;; esac

if [ "$FORCE" -ne 1 ] && [ -n "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]; then
  git -C "$REPO" status --short --untracked-files=no >&2
  die "Ada perubahan belum di-commit pada berkas terlacak. Commit/stash dulu, atau pakai --force."
fi

SYNC_DIRS="app simcore kb tests n8n_datatables scripts"
SYNC_FILES="requirements.txt Dockerfile railway.json .dockerignore .env.example README.md KUNCI_TRAINER.md"
[ "$WITH_DATA" -eq 1 ] && SYNC_DIRS="$SYNC_DIRS data"

# ---------------------------------------------------------------- daftar perubahan
LIST="$(mktemp)"; trap 'rm -f "$LIST"' EXIT
collect() {  # keluarkan path relatif semua berkas sumber yang masuk daftar sinkron
  local d f
  for d in $SYNC_DIRS; do
    if [ -d "$SOURCE/$d" ]; then
      ( cd "$SOURCE" && find "$d" -type f ! -name '*.pyc' ! -name '.DS_Store' ! -path '*/__pycache__/*' )
    fi
  done
  for f in $SYNC_FILES; do [ -f "$SOURCE/$f" ] && printf '%s\n' "$f"; done
  return 0
}
collect | sort | while IFS= read -r rel; do
  if [ ! -f "$REPO/$rel" ]; then
    printf 'BARU  %s\n' "$rel"
  elif ! cmp -s "$SOURCE/$rel" "$REPO/$rel"; then
    printf 'UBAH  %s\n' "$rel"
  fi
done > "$LIST"

N_CHANGED="$(wc -l < "$LIST" | tr -d ' ')"
say "Sumber : $SOURCE"
say "Repo   : $REPO"
if [ "$N_CHANGED" -eq 0 ]; then
  say "Repo sudah sama dengan versi terbaru. Tidak ada yang perlu diperbarui."
  exit 0
fi
say "Perubahan ($N_CHANGED berkas):"
sed 's/^/  /' "$LIST"

if [ "$DRY" -eq 1 ]; then
  say ""; say "[dry-run] Tidak ada yang disalin."
  exit 0
fi
say ""
confirm "Salin berkas di atas ke repo?" || { say "Dibatalkan. Repo tidak diubah."; exit 0; }

# ---------------------------------------------------------------- salin
BEFORE_HEAD="$(git -C "$REPO" rev-parse HEAD)"
while IFS= read -r line; do
  rel="${line#*  }"
  mkdir -p "$REPO/$(dirname "$rel")"
  cp -p "$SOURCE/$rel" "$REPO/$rel"
done < "$LIST"
chmod +x "$REPO"/scripts/*.sh 2>/dev/null || true

# .gitignore: pastikan rahasia dan lingkungan lokal tidak ikut terunggah
touch "$REPO/.gitignore"
for pat in ".env" ".venv/" "__pycache__/" "*.pyc" ".secrets/"; do
  grep -qxF "$pat" "$REPO/.gitignore" || printf '%s\n' "$pat" >> "$REPO/.gitignore"
done
say "Berkas disalin."

# ---------------------------------------------------------------- uji
if [ "$SKIP_TESTS" -eq 0 ]; then
  PY="python3"
  [ -x "$REPO/.venv/bin/python" ] && PY="$REPO/.venv/bin/python"
  say "Menjalankan smoke test dengan: $PY"
  if ! TEST_OUT="$(cd "$REPO" && "$PY" tests/smoke_test.py 2>&1)"; then
    printf '%s\n' "$TEST_OUT" | tail -15 >&2
    say ""
    say "Smoke test GAGAL. Perubahan disimpan ke stash supaya repo kembali bersih."
    git -C "$REPO" stash push -u -q -m "update_code gagal uji $(date +%Y%m%d-%H%M%S)" || true
    say "Untuk melihat/menghapusnya: git stash list | git stash drop"
    exit 1
  fi
  printf '%s\n' "$TEST_OUT" | tail -2
fi

# ---------------------------------------------------------------- commit
PATHS=""
for d in $SYNC_DIRS; do [ -e "$REPO/$d" ] && PATHS="$PATHS $d"; done
for f in $SYNC_FILES .gitignore; do [ -e "$REPO/$f" ] && PATHS="$PATHS $f"; done
# shellcheck disable=SC2086
git -C "$REPO" add -A -- $PATHS
if git -C "$REPO" diff --cached --quiet; then
  say "Tidak ada perubahan untuk di-commit."
else
  say ""
  git -C "$REPO" diff --cached --stat | tail -15
  say ""
  confirm "Commit dengan pesan: \"$MSG\" ?" || { say "Dibatalkan. Perubahan tetap ada di staging; batalkan dengan: git -C $REPO reset"; exit 0; }
  git -C "$REPO" commit -q -m "$MSG"
  say "Commit dibuat: $(git -C "$REPO" rev-parse --short HEAD)"
fi

# ---------------------------------------------------------------- deploy
case "$DEPLOY" in
  none)
    say "Deploy dilewati (--deploy none)."
    exit 0 ;;
  push)
    say "Mendorong ke GitHub ..."
    if ! git -C "$REPO" push 2>/dev/null; then
      git -C "$REPO" push -u origin HEAD || die "git push gagal. Cek remote dan izin GitHub."
    fi
    say "Terdorong. Railway otomatis deploy HANYA bila integrasi GitHub-nya sehat"
    say "(di Settings tidak ada 'Auto deploy unavailable'). Kalau tidak, jalankan ulang dengan --deploy up." ;;
  up)
    command -v railway >/dev/null 2>&1 || die "Railway CLI belum terpasang"
    say "Mengunggah dan men-deploy lewat Railway CLI ..."
    ( cd "$REPO" && railway up --detach --service "$SERVICE" -m "$MSG" ) ;;
esac

# ---------------------------------------------------------------- periksa deploy
command -v curl >/dev/null 2>&1 || { say "curl tidak ada; periksa $BASE/health secara manual."; exit 0; }
# Versi yang diharapkan dibaca dari main.py di repo (setelah disalin). Memeriksa field yang
# sudah ada di rilis lama (mis. kunci_dimuat) akan salah mengira kode baru sudah aktif.
EXPECT_VER="$(sed -n 's/^APP_VERSION *= *"\(.*\)".*/\1/p' "$REPO/app/main.py" | head -1)"
new_code_live() {  # tanpa pipeline: aman terhadap pipefail
  local out; out="$(curl -s -m 15 "$BASE/health" || true)"
  if [ -n "$EXPECT_VER" ]; then
    case "$out" in
      *"\"versi\":\"$EXPECT_VER\""*|*"\"versi\": \"$EXPECT_VER\""*) return 0 ;;
      *) return 1 ;;
    esac
  fi
  case "$out" in *kunci_dimuat*) return 0 ;; *) return 1 ;; esac
}
if [ -n "$EXPECT_VER" ]; then
  say "Menunggu kode versi $EXPECT_VER aktif di $BASE (maks ${WAIT_MAX}s) ..."
else
  say "Menunggu kode baru aktif di $BASE (maks ${WAIT_MAX}s; tanpa penanda versi, pemeriksaan kurang tegas) ..."
fi
DEADLINE=$(( $(date +%s) + WAIT_MAX ))
until new_code_live; do
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then
    echo "Waktu habis: /health belum menunjukkan versi ${EXPECT_VER:-baru} (kode baru belum aktif)." >&2
    echo "Cek Railway -> Deployments. Bila memakai --deploy push, kemungkinan auto-deploy belum aktif: pakai --deploy up." >&2
    exit 1
  fi
  sleep "$POLL"
done
say "Kode baru aktif. Hasil /health:"
curl -s -m 15 "$BASE/health"; echo
