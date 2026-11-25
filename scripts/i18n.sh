#!/usr/bin/env bash
# Collects the app's texts into po/stickler.pot and merges them into every po/<lang>.po.
# Run it after changing a text; then translate the new or fuzzy entries in each po/<lang>.po
# (the languages are listed in po/LINGUAS).
# Needs gettext (xgettext, msgmerge, msginit). Later Weblate commits the .po files itself.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

mapfile -t sources < <(git ls-files --cached --others --exclude-standard 'src/stickler_gtk/*.py' 'src/stickler_app/*.py' | sort)
xgettext --language=Python --from-code=UTF-8 --keyword=_ --keyword=N_ --keyword=ngettext:1,2 \
  --add-comments=Translators --sort-by-file --package-name=Stickler \
  --msgid-bugs-address=https://github.com/niklastshiang/stickler/issues \
  --output=po/stickler.pot "${sources[@]}"
sed -i 's/charset=CHARSET/charset=UTF-8/' po/stickler.pot

mapfile -t languages < <(grep -v '^#' po/LINGUAS)  # one language code per line
for lang in "${languages[@]}"; do
  if [[ ! -f "po/$lang.po" ]]; then
    msginit --no-translator --locale="$lang" --input=po/stickler.pot --output-file="po/$lang.po"
  fi
  msgmerge --quiet --update --backup=none --previous "po/$lang.po" po/stickler.pot
  msgattrib --no-obsolete --output-file="po/$lang.po" "po/$lang.po"  # drop removed texts
done
echo "po/stickler.pot: $(grep -c '^msgid ' po/stickler.pot) entries (including the header)"
# the Mac app's String Catalog follows po/ (SPEC.md, module `shared-core`)
uv run python scripts/xcstrings.py
# and the Windows app's string tables (SPEC.md, module `win-shell`)
uv run python scripts/winstrings.py
