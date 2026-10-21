path="${1:-.}"
if [[ ! -e "$path" ]]; then
  printf 'does not exist\n'
  exit 0
fi
# Absolute paths also protect tools whose option parsers lack an end marker.
path="$(realpath -- "$path")"
if [[ -d "$path" ]]; then
  lsd --tree --depth=3 -- "$path"
elif [[ -f "$path" ]]; then
  mime="$(file --brief --mime-type -- "$path")"
  case "$mime" in
    image/*)
      if identify "$path" >/dev/null 2>&1; then
        viu -- "$path"
      else
        bat --color=always -- "$path"
      fi
      ;;
    application/pdf)
      if pdfinfo "$path" >/dev/null 2>&1; then
        pdftotext -l 10 "$path" -
      else
        bat --color=always -- "$path"
      fi
      ;;
    *) bat --color=always -- "$path" ;;
  esac
fi
