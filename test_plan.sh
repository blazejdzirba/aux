#!/usr/bin/env bash
# Weryfikacja wdrozenia planu (czern-zloto, zasoby, prompty, optimizer-model, spinner)
B=http://127.0.0.1:8000
P=0; F=0
ok()   { echo "OK  $1"; P=$((P+1)); }
fail() { echo "FAIL $1"; F=$((F+1)); }
chk()  { if [ "$2" = "1" ]; then ok "$1"; else fail "$1"; fi; }

sleep 2

# 1. start + health
chk "/health -> 200" "$(curl -s -o /dev/null -w '%{http_code}' $B/health | grep -c 200)"

# 2. motyw czern-zloto dolaczony + nowy sidebar
HTML=$(curl -s $B/models)
chk "theme.css podpiety"      "$(echo "$HTML" | grep -c 'theme.css?v=1')"
chk "spinner.css podpiety"    "$(echo "$HTML" | grep -c 'spinner.css?v=1')"
chk "brand: Vibe Center"      "$(echo "$HTML" | grep -c 'Vibe Center')"
chk "sekcja: Baza wiedzy"     "$(echo "$HTML" | grep -c 'Baza wiedzy')"
chk "sekcja: Zasoby"          "$(echo "$HTML" | grep -c '>Zasoby<')"
chk "sekcja: Praca"           "$(echo "$HTML" | grep -c '>Praca<')"
chk "link /resources"         "$(echo "$HTML" | grep -c 'href="/resources"')"
chk "link /prompts"           "$(echo "$HTML" | grep -c 'href="/prompts"')"
chk "link /optimizer"  "$(echo "$HTML" | grep -c 'href="/optimizer"')"
chk "brak zepsutych linkow (learn/cheatsheets/projects/stacks)" "$(echo "$HTML" | grep -cE 'href="/(learn|cheatsheets|projects|stacks)"')"

# 3. nowy motyw w css (zloto)
chk "theme.css: --color-accent #d4af37" "$(grep -c 'color-accent: #d4af37' static/theme.css)"
chk "theme.css: gradient tla"           "$(grep -c 'radial-gradient' static/theme.css)"
chk "spinner.css: @keyframes spin"      "$(grep -c '@keyframes spin' static/spinner.css)"

# 4. Zasoby: widok + zakladki + CRUD
R=$(curl -s $B/resources)
chk "/resources 200 + h1"          "$(echo "$R" | grep -c 'Zasoby</h1>')"
chk "zakladki links/notes/tools"   "$(echo "$R" | grep -c "tab === 'tools'")"
chk "formularz linkow hx-post"     "$(echo "$R" | grep -c 'hx-post="/resources/links"')"
ID=$(curl -s -o /dev/null -w '%{http_code}' -X POST $B/resources/links --data-urlencode "title=Test Zasob" --data-urlencode "url=https://example.com" --data-urlencode "category=test" | grep -c 200)
chk "POST /resources/links"        "$ID"
LID=$(sqlite3 data/aux.db "SELECT id FROM resource_links WHERE title='Test Zasob' ORDER BY id DESC LIMIT 1;")
chk "link widoczny na liscie"      "$(curl -s $B/resources | grep -c "Test Zasob")"
chk "DELETE linka"                 "$(curl -s -o /dev/null -w '%{http_code}' -X DELETE $B/resources/links/$LID | grep -c 200)"
chk "rekord usuniety z DB"         "$(sqlite3 data/aux.db "SELECT COUNT(*) FROM resource_links WHERE title='Test Zasob';")" # oczekiwane 0

# 5. Prompty: widok + zapis z optymalizatora
chk "/prompts 200"                 "$(curl -s -o /dev/null -w '%{http_code}' $B/prompts | grep -c 200)"
S=$(curl -s -X POST $B/prompts/save --data-urlencode "title=Plan Test" --data-urlencode "content=TRESC TESTOWA" --data-urlencode "mode=standard")
chk "POST /prompts/save -> Zapisano" "$(echo "$S" | grep -c 'Zapisano w Promptach')"
chk "prompt widoczny na /prompts"  "$(curl -s $B/prompts | grep -c 'TRESC TESTOWA')"
PID=$(sqlite3 data/aux.db "SELECT id FROM saved_prompts WHERE title='Plan Test';")
chk "DELETE prompta"               "$(curl -s -o /dev/null -w '%{http_code}' -X DELETE $B/prompts/$PID | grep -c 200)"

# 6. Playground (Chat UI) i Optymalizator: calkiem osobne strony
PG=$(curl -s $B/playground)
OP=$(curl -s $B/optimizer)
chk "/playground: chat UI"                    "$(echo "$PG" | grep -c 'chat-page')"
chk "/playground: endpoint czatu"             "$(echo "$PG" | grep -c '/playground/chat')"
chk "/playground: przycisk Wyczyść czat"      "$(echo "$PG" | grep -c 'Wyczyść czat')"
chk "/playground: markdown (marked)"          "$(echo "$PG" | grep -c 'marked@12')"
chk "/playground: brak optymalizatora"        "$(if echo "$PG" | grep -q 'hx-post="/optimizer/optimize"'; then echo 0; else echo 1; fi)"
chk "/optimizer: formularz optymalizatora"     "$(echo "$OP" | grep -c 'hx-post="/optimizer/optimize"')"
chk "/optimizer: brak playground"              "$(if echo "$OP" | grep -q 'playground-result'; then echo 0; else echo 1; fi)"
chk "/models: brak tab: 'playground'"          "$(if curl -s $B/models | grep -q "tab: 'playground'"; then echo 0; else echo 1; fi)"
chk "/prompt-optimizer -> redirect 302"        "$(curl -s -o /dev/null -w '%{http_code}' $B/prompt-optimizer | grep -c 302)"

# 7. Settings: dropdown modelu optymalizatora
ST=$(curl -s $B/settings)
chk "sekcja Model optymalizatora"  "$(echo "$ST" | grep -c 'Model optymalizatora promptów')"
chk "formularz optimizer-model"    "$(echo "$ST" | grep -c '/settings/optimizer-model')"

# 8. model_row: spinner
chk "model_row: hx-indicator + spinner" "$(grep -c 'htmx-indicator' templates/partials/model_row.html)"

# 9. stare strony nie zepsute
for p in documents vault; do
  chk "/$p 200" "$(curl -s -o /dev/null -w '%{http_code}' $B/$p | grep -c 200)"
done

echo ""
echo "=== WYNIK: $P OK, $F FAIL ==="
