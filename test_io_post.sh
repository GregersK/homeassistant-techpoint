#!/usr/bin/env bash
# Test different POST body formats for /config/io/userdefined
# Usage: bash test_io_post.sh <output_id> <username> <password> [base_url]
# Example: bash test_io_post.sh 831 admin secret https://10.8.100.5/api/v1

OUTPUT_ID="${1:?Usage: $0 <output_id> <username> <password> [base_url]}"
USERNAME="${2:?}"
PASSWORD="${3:?}"
BASE="${4:-https://10.8.100.5/api/v1}"
URL="$BASE/config/io/userdefined"

do_post() {
    local url="$1"
    local body="$2"
    curl -k -s -X POST "$url" \
        -u "$USERNAME:$PASSWORD" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json" \
        -d "$body" 2>&1
}

try() {
    local label="$1"
    local body="$2"
    echo "=== $label ==="
    echo "Body: $body"
    echo "Response: $(do_post "$URL" "$body")"
    echo ""
}

echo "Testing POST $URL with output_id=$OUTPUT_ID"
echo ""

# 1. Spec: string id, per-item status
try "1. spec string id + per-item status" \
    "{\"ids\":[{\"id\":\"$OUTPUT_ID\",\"status\":2}]}"

# 2. Integer id, per-item status
try "2. integer id + per-item status" \
    "{\"ids\":[{\"id\":$OUTPUT_ID,\"status\":2}]}"

# 3. Bare int array + top-level status
try "3. bare int array + top-level status" \
    "{\"ids\":[$OUTPUT_ID],\"status\":2}"

# 4. Mirror GET response: state field
try "4. state field (mirrors GET response)" \
    "{\"ids\":[{\"id\":$OUTPUT_ID,\"state\":2}]}"

# 5. userDefinedIO single object
try "5. userDefinedIO single object" \
    "{\"userDefinedIO\":{\"id\":$OUTPUT_ID,\"state\":2}}"

# 6. userDefinedIOs array (mirrors GET wrapper key)
try "6. userDefinedIOs array" \
    "{\"userDefinedIOs\":[{\"id\":$OUTPUT_ID,\"state\":2}]}"

# 7. ioCommand wrapper + ioIDs nested
try "7. ioCommand + ioIDs nested" \
    "{\"ioCommand\":{\"ioIDs\":{\"ids\":[{\"id\":$OUTPUT_ID}]},\"status\":2}}"

# 8. With ?ioType=29 query param
echo "=== 8. ioType=29 query param + integer id/status ==="
echo "Body: {\"ids\":[{\"id\":$OUTPUT_ID,\"status\":2}]}"
echo "Response: $(do_post "${URL}?ioType=29" "{\"ids\":[{\"id\":$OUTPUT_ID,\"status\":2}]}")"
echo ""

# 9. Empty ids + params on query string
echo "=== 9. empty ids body + params on query string ==="
echo "Body: {\"ids\":[]}"
echo "Response: $(do_post "${URL}?ioType=29&id=$OUTPUT_ID&status=2" '{"ids":[]}')"
echo ""

# 10. PUT with full-record style
echo "=== 10. PUT (not POST) with state field ==="
result=$(curl -k -s -X PUT "$URL" \
    -u "$USERNAME:$PASSWORD" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d "{\"id\":$OUTPUT_ID,\"state\":2}" 2>&1)
echo "Body: {\"id\":$OUTPUT_ID,\"state\":2}"
echo "Response: $result"
echo ""

# 11. No body whatsoever
echo "=== 11. POST with no body ==="
result=$(curl -k -s -X POST "$URL" \
    -u "$USERNAME:$PASSWORD" \
    -H "Accept: application/json" 2>&1)
echo "Response: $result"
echo ""

echo "=== Done. Find the response WITHOUT RapidJson in it ==="
