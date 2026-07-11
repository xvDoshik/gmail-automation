from __future__ import annotations

import json
import zipfile
from pathlib import Path

def write_proxy_extension_zip(
    proxy: dict[str, str], out_zip: Path, *, socks5: bool
) -> None:
    port_n = int(str(proxy["port"]).strip())
    scheme_js = "socks5" if socks5 else "http"
    manifest = """{
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Proxy Auth",
        "permissions": ["proxy", "webRequest", "webRequestBlocking", "<all_urls>"],
        "background": { "scripts": ["bg.js"] }
    }"""
    host_js = json.dumps(proxy["host"])
    user_js = json.dumps(proxy["user"])
    pass_js = json.dumps(proxy["password"])
    bg = (
        "chrome.proxy.settings.set({\n"
        "    value: {\n"
        "        mode: \"fixed_servers\",\n"
        "        rules: {\n"
        "            singleProxy: {\n"
        f"                scheme: \"{scheme_js}\",\n"
        f"                host: {host_js},\n"
        f"                port: {port_n}\n"
        "            },\n"
        "            bypassList: [\"localhost\", \"127.0.0.1\"]\n"
        "        }\n"
        "    },\n"
        "    scope: \"regular\"\n"
        "}, function(){});\n"
        "\n"
        "chrome.webRequest.onAuthRequired.addListener(\n"
        "    function(details) {\n"
        "        return {\n"
        "            authCredentials: {\n"
        f"                username: {user_js},\n"
        f"                password: {pass_js}\n"
        "            }\n"
        "        };\n"
        "    },\n"
        "    { urls: [\"<all_urls>\"] },\n"
        "    [\"blocking\"]\n"
        ");\n"
    )
    with zipfile.ZipFile(out_zip, "w") as z:
        z.writestr("manifest.json", manifest)
        z.writestr("bg.js", bg)
