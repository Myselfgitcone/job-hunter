import json, base64, gzip, re

with open(r'C:\Users\jagad\Downloads\Job Hunter (standalone).html', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract and save template
tmpl_match = re.search(r'type="__bundler/template">(.*?)</script>', content, re.DOTALL)
if tmpl_match:
    template = json.loads(tmpl_match.group(1))
    with open('design_template.html', 'w', encoding='utf-8') as f:
        f.write(template)
    print(f"Saved design_template.html ({len(template)} chars)")

# Extract and decompress all JS assets
manifest_match = re.search(r'type="__bundler/manifest">(.*?)</script>', content, re.DOTALL)
if manifest_match:
    manifest = json.loads(manifest_match.group(1))
    print(f"Found {len(manifest)} assets")
    all_code = ""
    for i, (uuid, entry) in enumerate(manifest.items()):
        if 'javascript' in entry['mime']:
            try:
                data = base64.b64decode(entry['data'])
                if entry.get('compressed'):
                    data = gzip.decompress(data)
                code = data.decode('utf-8')
                all_code += f"\n\n// === ASSET {i+1}: {uuid} ===\n" + code
            except Exception as e:
                print(f"Error asset {i}: {e}")
    
    with open('design_code.js', 'w', encoding='utf-8') as f:
        f.write(all_code)
    print(f"Saved design_code.js ({len(all_code)} chars)")
