#!/usr/bin/env bash
# rotate_keys.sh - Ganti semua API key SCADA Sim API di Railway.
#
# Yang dikerjakan:
#   1. Membuat key acak baru: grup-1..grup-N dan trainer.
#   2. Menyimpannya ke file lokal berizin 600 di .secrets/ (otomatis masuk .gitignore).
#   3. Mengubah variabel API_KEYS di Railway lewat stdin (key tidak muncul di daftar proses).
#   4. Menunggu deployment baru, lalu memeriksa: key baru diterima, dev-key (dan key lama) ditolak.
#
# Pemakaian (jalankan dengan bash, dari folder repo, setelah `railway login` dan `railway link`):
#   bash scripts/rotate_keys.sh --dry-run          # lihat rencana tanpa mengubah apa pun
#   bash scripts/rotate_keys.sh --check-old        # ganti key + pastikan key lama sudah mati
#
# Opsi:
#   --service NAMA   nama service Railway (default: pln-scada-sim)
#   --url URL        alamat publik API (default: variabel BASE atau alamat produksi)
#   --groups N       jumlah kelompok (default: 4)
#   --out-dir DIR    folder file key lokal (default: .secrets)
#   --wait DETIK     batas tunggu deployment baru (default: 300)
#   --check-old      minta key trainer LAMA (diketik tersembunyi) untuk memastikan ia ditolak
#   --show           cetak key lengkap ke layar (default: hanya disamarkan)
#   --no-verify      lewati pemeriksaan setelah deploy
#   --dry-run        tidak menulis file dan tidak memanggil Railway
#   --yes            lewati pertanyaan konfirmasi
set -euo pipefail

SERVICE="pln-scada-sim"
BASE="${BASE:-https://pln-scada-sim-production.up.railway.app}"
N_GROUPS=4
OUT_DIR=".secrets"
WAIT_MAX=300
POLL="${POLL_INTERVAL:-10}"
DRY=0; YES=0; SHOW=0; VERIFY=1; CHECK_OLD=0
FAILS=0

usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --service)   SERVICE="${2:?}"; shift 2 ;;
    --url)       BASE="${2:?}"; shift 2 ;;
    --groups)    N_GROUPS="${2:?}"; shift 2 ;;
    --out-dir)   OUT_DIR="${2:?}"; shift 2 ;;
    --wait)      WAIT_MAX="${2:?}"; shift 2 ;;
    --check-old) CHECK_OLD=1; shift ;;
    --show)      SHOW=1; shift ;;
    --no-verify) VERIFY=0; shift ;;
    --dry-run)   DRY=1; shift ;;
    --yes|-y)    YES=1; shift ;;
    -h|--help)   usage; exit 0 ;;
    *) echo "Opsi tidak dikenal: $1" >&2; usage >&2; exit 2 ;;
  esac
done
BASE="${BASE%/}"

case "$N_GROUPS" in ''|*[!0-9]*) echo "--groups harus angka" >&2; exit 2 ;; esac
[ "$N_GROUPS" -ge 1 ] || { echo "--groups minimal 1" >&2; exit 2; }

say() { printf '%s\n' "$*"; }
ok()  { printf '  [LULUS] %s\n' "$*"; }
bad() { printf '  [GAGAL] %s\n' "$*"; FAILS=$((FAILS+1)); }

gen_key() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_urlsafe(24))'
  elif command -v openssl >/dev/null 2>&1; then
    ( set +o pipefail; openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 32; echo )
  else
    ( set +o pipefail; LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32; echo )
  fi
}

mask() { local k="$1"; printf '%s********' "${k:0:4}"; }

# ---------------------------------------------------------------- 1. buat key
NAMES=""
i=1
while [ "$i" -le "$N_GROUPS" ]; do NAMES="$NAMES grup-$i"; i=$((i+1)); done
NAMES="$NAMES trainer"

PAIRS=""
for n in $NAMES; do
  k="$(gen_key)"
  PAIRS="${PAIRS}${n}:${k}"$'\n'
done
API_KEYS="$(printf '%s' "$PAIRS" | sed '/^$/d' | paste -sd, -)"

# validasi bentuk: nama:key, key 24+ karakter aman, tidak ada duplikat
EXPECT=$((N_GROUPS+1))
COUNT=0
while IFS= read -r line; do
  [ -z "$line" ] && continue
  if ! [[ "$line" =~ ^[a-z0-9-]+:[A-Za-z0-9_-]{24,}$ ]]; then
    echo "Key tidak lolos validasi bentuk (tidak boleh ada spasi, koma, atau titik dua tambahan)." >&2
    exit 1
  fi
  COUNT=$((COUNT+1))
done <<PAIRS_END
$PAIRS
PAIRS_END
[ "$COUNT" -eq "$EXPECT" ] || { echo "Jumlah key salah ($COUNT, seharusnya $EXPECT)" >&2; exit 1; }
DUP="$(printf '%s' "$PAIRS" | sed '/^$/d' | cut -d: -f2 | sort | uniq -d)"
[ -z "$DUP" ] || { echo "Ada key kembar, ulangi." >&2; exit 1; }

TRAINER_KEY="$(printf '%s' "$PAIRS" | sed -n 's/^trainer://p')"

say "Service Railway : $SERVICE"
say "Alamat API      : $BASE"
say "Key baru dibuat (disamarkan):"
while IFS=: read -r n k; do
  [ -z "$n" ] && continue
  if [ "$SHOW" -eq 1 ]; then say "  $n  $k"; else say "  $n  $(mask "$k")"; fi
done <<PAIRS_END
$PAIRS
PAIRS_END

# ---------------------------------------------------------------- dry run
if [ "$DRY" -eq 1 ]; then
  say ""
  say "[dry-run] Tidak ada yang ditulis atau diubah. Langkah yang akan dijalankan:"
  say "  1. Simpan key lengkap ke $OUT_DIR/api-keys-<waktu>.env (izin 600, masuk .gitignore)"
  say "  2. railway variable set API_KEYS --stdin --service $SERVICE   (memicu deploy ulang)"
  say "  3. Tunggu sampai key trainer baru diterima di $BASE (maks ${WAIT_MAX}s)"
  say "  4. Cek: dev-key ditolak, key lama ditolak (dengan --check-old), semua key baru diterima"
  exit 0
fi

# ---------------------------------------------------------------- 2. prasyarat
command -v railway >/dev/null 2>&1 || { echo "Railway CLI belum terpasang (npm i -g @railway/cli)." >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "curl tidak ditemukan." >&2; exit 1; }
railway status >/dev/null 2>&1 || { echo "Belum login atau belum link. Jalankan: railway login && railway link" >&2; exit 1; }

if [ "$YES" -ne 1 ]; then
  say ""
  say "Peringatan: key LAMA langsung tidak berlaku setelah deploy selesai."
  say "Credential Header Auth di n8n yang memakai key lama harus diganti."
  printf 'Lanjut mengganti API_KEYS pada service "%s"? [y/N] ' "$SERVICE"
  read -r ans
  case "$ans" in y|Y|yes|YES) ;; *) say "Dibatalkan. Tidak ada yang berubah."; exit 0 ;; esac
fi

CHECK_OLD_KEY=""
if [ "$CHECK_OLD" -eq 1 ]; then
  printf 'Key trainer LAMA (diketik tersembunyi, Enter jika dilewati): '
  read -rs CHECK_OLD_KEY || true
  echo
fi

# ---------------------------------------------------------------- 3. simpan file lokal
umask 077
mkdir -p "$OUT_DIR"
OUT_FILE="$OUT_DIR/api-keys-$(date +%Y%m%d-%H%M%S).env"
{
  echo "# Dibuat $(date '+%Y-%m-%d %H:%M:%S %z'). JANGAN di-commit atau dibagikan."
  echo "API_KEYS=$API_KEYS"
  while IFS=: read -r n k; do
    [ -z "$n" ] && continue
    echo "KEY_$(printf '%s' "$n" | tr 'a-z-' 'A-Z_')=$k"
  done <<PAIRS_END
$PAIRS
PAIRS_END
} > "$OUT_FILE"
chmod 600 "$OUT_FILE"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  ROOT="$(git rev-parse --show-toplevel)"
  touch "$ROOT/.gitignore"
  grep -qxF "$OUT_DIR/" "$ROOT/.gitignore" || printf '%s/\n' "$OUT_DIR" >> "$ROOT/.gitignore"
else
  say "Catatan: folder ini bukan repo git; pastikan $OUT_DIR/ tidak ikut terunggah ke mana pun."
fi
say ""
say "Key lengkap disimpan di: $OUT_FILE (izin 600)"

# ---------------------------------------------------------------- 4. ubah variabel di Railway
redact() { sed "s|$API_KEYS|[API_KEYS disembunyikan]|g"; }

set_api_keys() {
  local e1 e2
  if e1="$(printf '%s' "$API_KEYS" | railway variable set API_KEYS --stdin --service "$SERVICE" 2>&1)"; then
    return 0
  fi
  if e2="$(printf '%s' "$API_KEYS" | railway variables --set-from-stdin API_KEYS --service "$SERVICE" 2>&1)"; then
    return 0
  fi
  echo "Gagal mengubah variabel API_KEYS di Railway." >&2
  printf -- '--- sintaks baru:\n%s\n' "$e1" | redact >&2
  printf -- '--- sintaks lama:\n%s\n' "$e2" | redact >&2
  return 1
}

say "Mengubah API_KEYS di Railway ..."
if ! set_api_keys; then
  say "Variabel TIDAK berubah, jadi key lama masih berlaku. File $OUT_FILE boleh dihapus."
  exit 1
fi
say "Variabel diubah; Railway memulai deployment baru."

if [ "$VERIFY" -ne 1 ]; then
  say "Selesai (tanpa verifikasi). Key ada di $OUT_FILE"
  exit 0
fi

# ---------------------------------------------------------------- 5. verifikasi
# Key dikirim lewat berkas header sementara, bukan argumen curl.
http_code() {  # $1=path  $2=key
  local hf code
  hf="$(mktemp)"; chmod 600 "$hf"
  printf 'X-API-Key: %s\n' "$2" > "$hf"
  code="$(curl -s -o /dev/null -m 15 -w '%{http_code}' -H @"$hf" "$BASE$1" || true)"
  rm -f "$hf"
  printf '%s' "${code:-000}"
}

say "Menunggu deployment baru (maks ${WAIT_MAX}s). Pemuatan MySQL bisa 1-2 menit ..."
DEADLINE=$(( $(date +%s) + WAIT_MAX ))
until [ "$(http_code /api/v1/substations "$TRAINER_KEY")" = "200" ]; do
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then
    echo "Waktu habis: key trainer baru belum diterima di $BASE." >&2
    echo "Cek Railway -> $SERVICE -> Deployments -> Deploy Logs. Key baru ada di $OUT_FILE" >&2
    exit 1
  fi
  sleep "$POLL"
done

say "Pemeriksaan:"
for n in $NAMES; do
  k="$(printf '%s' "$PAIRS" | sed -n "s/^$n://p")"
  c="$(http_code /api/v1/substations "$k")"
  if [ "$c" = "200" ]; then ok "key $n diterima (HTTP 200)"; else bad "key $n -> HTTP $c (seharusnya 200)"; fi
done
c="$(http_code /api/v1/substations dev-key)"
if [ "$c" = "403" ]; then ok "dev-key ditolak (HTTP 403)"; else bad "dev-key -> HTTP $c (seharusnya 403)"; fi
if [ -n "$CHECK_OLD_KEY" ]; then
  c="$(http_code /api/v1/substations "$CHECK_OLD_KEY")"
  if [ "$c" = "403" ]; then ok "key trainer lama ditolak (HTTP 403)"; else bad "key trainer lama -> HTTP $c (seharusnya 403)"; fi
fi
c="$(http_code /api/v1/substations tidak-ada)"
if [ "$c" = "403" ]; then ok "key acak ditolak (HTTP 403)"; else bad "key acak -> HTTP $c (seharusnya 403)"; fi

say ""
if [ "$FAILS" -gt 0 ]; then
  say "$FAILS pemeriksaan gagal. Lihat Deploy Logs dan isi variabel API_KEYS di Railway."
  exit 1
fi
say "Semua pemeriksaan lulus."
say ""
say "Langkah berikutnya:"
say "  1. Salin key dari $OUT_FILE ke password manager (jangan ke chat atau dokumen)."
say "  2. Perbarui credential Header Auth (X-API-Key) di n8n: satu per kelompok + trainer."
say "  3. Setelah tersimpan aman, hapus file lokalnya:  rm $OUT_FILE"
