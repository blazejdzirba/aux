#!/usr/bin/env bash
# Finalne testy całości — Prompt 9
B=http://127.0.0.1:8000

echo "=== 1. health i static ==="
curl -s $B/health
echo
curl -s -o /dev/null -w "/static/app.css -> HTTP %{http_code}\n" $B/static/app.css

echo "=== 2. wszystkie strony GET ==="
for p in / /models /playground /documents /settings; do
  curl -s -o /dev/null -w "$p -> HTTP %{http_code}\n" $B$p
done

echo "=== 3. sidebar aktywny na kazdej stronie ==="
for p in models playground documents settings; do
  curl -s $B/$p | grep -o "nav-item active\" href=\"/$p\"" | head -1
done

echo "=== 4. flow /models ==="
sqlite3 data/aux.db "INSERT INTO ai_models (provider_id, model_id, display_name) VALUES (1, 'test/final-model', 'Final Test');"
MID=$(sqlite3 data/aux.db "SELECT id FROM ai_models WHERE model_id='test/final-model';")
curl -s $B/models | grep -o "test/final-model" | head -1
curl -s -X POST $B/models/$MID/test -H "HX-Request: true" | grep -o "id=\"model-$MID\"" | head -1
curl -s -o /dev/null -w "POST delete -> HTTP %{http_code}\n" -X POST $B/models/$MID/delete

echo "=== 5. flow /documents ==="
curl -s -o /dev/null -X POST $B/documents --data-urlencode "title=Final DOC"
DID=$(sqlite3 data/aux.db "SELECT id FROM documents ORDER BY id DESC LIMIT 1;")
curl -s -X PUT "$B/documents/$DID" -H "HX-Request: true" --data-urlencode "title=Final DOC v2" --data-urlencode "content=## Test" | grep -o 'Zapisano ✓'
curl -s "$B/documents/$DID" | grep -o '<h2>Test</h2>'
curl -s -o /dev/null -w "DELETE doc -> HTTP %{http_code}\n" -X DELETE "$B/documents/$DID" -H "HX-Request: true"

echo "=== 6. flow /settings + playground z kluczem ==="
curl -s -X POST $B/settings/omniroute-key --data-urlencode "api_key=sk-or-final-test" | grep -o 'Zapisano ✓'
sqlite3 data/aux.db "INSERT INTO ai_models (provider_id, model_id) VALUES (1, 'test/pg-final');"
PID=$(sqlite3 data/aux.db "SELECT id FROM ai_models WHERE model_id='test/pg-final';")
curl -s -X POST $B/playground/run --data-urlencode "model_id=$PID" --data-urlencode "prompt=Hej" | grep -oE 'HTTP 40[0-9]: [^<]{0,40}' | head -1

echo "=== cleanup ==="
sqlite3 data/aux.db "DELETE FROM ai_models WHERE model_id LIKE 'test/%'; DELETE FROM documents WHERE title LIKE 'Final%';"
curl -s -X POST $B/settings/omniroute-key --data-urlencode "api_key=" > /dev/null
curl -s $B/health
echo
