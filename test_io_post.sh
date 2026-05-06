#!/usr/bin/env bash
# Test different POST body formats for /config/io/userdefined
# Usage: bash test_io_post.sh <output_id> <username> <password>
# Example: bash test_io_post.sh 123 admin secret

OUTPUT_ID="${1:?Usage: $0 <output_id> <username> <password>}"
USERNAME="${2:?}"
PASSWORD="${3:?}"
BASE="https://10.8.100.5/api/v1"
URL="$BASE/config/io/userdefined"
AUTH="-u $USERNAME:$PASSWORD"
CURL="curl -k -s -X POST $URL $AUTH -H Content-Type:application/json"

try() {
    local label="$1"; local body="$2"
    echo "=== $label ==="
    echo "Body: $body"
    result=$($CURL -d "$body" 2>&1)
    echo "Response: $result"
    echo ""
}

echo "Testing POST $URL with output_id=$OUTPUT_ID"
echo ""

# 1. Spec format: string id, per-item status
try "1. Spec: [{id:str, status:int}]" \
    "{\"ids\":[{\"id\":\"$OUTPUT_ID\",\"status\":2}]}"

# 2. Integer id, per-item status
try "2. [{id:int, status:int}]" \
    "{\"ids\":[{\"id\":$OUTPUT_ID,\"status\":2}]}"

# 3. Bare int array + top-level status
try "3. [int] + top-level status" \
    "{\"ids\":[$OUTPUT_ID],\"status\":2}"

# 4. TechPoint nested ioIDs pattern
try "4. ioIDs nested + top-level status" \
    "{\"ioIDs\":{\"ids\":[{\"id\":$OUTPUT_ID}]},\"status\":2}"

# 5. userDefinedIO single object (PUT-style)
try "5. userDefinedIO:{id,state}" \
    "{\"userDefinedIO\":{\"id\":$OUTPUT_ID,\"state\":2}}"

# 6. userDefinedIOs array (mirrors GET response key)
try "6. userDefinedIOs:[{id,state}]" \
    "{\"userDefinedIOs\":[{\"id\":$OUTPUT_ID,\"state\":2}]}"

# 7. ioCommand wrapper
try "7. ioCommand:{ids:[{id,status}]}" \
    "{\"ioCommand\":{\"ids\":[{\"id\":$OUTPUT_ID,\"status\":2}]}}"

# 8. userdefinedio wrapper (OpenAPI schema name)
try "8. userdefinedio:{ids:[{id:str,status}]}" \
    "{\"userdefinedio\":{\"ids\":[{\"id\":\"$OUTPUT_ID\",\"status\":2}]}}"

# 9. id as nested object {id:{id:N}}
try "9. ids:[{id:{id:int},status}]" \
    "{\"ids\":[{\"id\":{\"id\":$OUTPUT_ID},\"status\":2}]}"

# 10. With ioType in body + spec format
try "10. ioType in body + spec" \
    "{\"ioType\":29,\"ids\":[{\"id\":\"$OUTPUT_ID\",\"status\":2}]}"

