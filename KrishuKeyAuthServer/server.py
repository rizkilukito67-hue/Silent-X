import os
import sys
import json
import time
import hmac
import sqlite3
import hashlib
import secrets
import threading
from datetime import datetime, timedelta
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

PORT = int(os.environ.get("PORT", 5000))
HOST = "0.0.0.0"
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keyauth.db")

# Thread-local storage for SQLite connections
_db_lock = threading.Lock()

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def init_db():
    with _db_lock:
        conn = get_db()
        cur = conn.cursor()
        
        # 1. Apps table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS apps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                owner_id TEXT NOT NULL,
                secret TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '1.0.0',
                announcement TEXT DEFAULT 'Welcome to Krishu X Cheats!',
                download_url TEXT DEFAULT '',
                status TEXT DEFAULT 'enabled',
                created_at TEXT NOT NULL
            )
        """)
        
        # 2. Users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                level TEXT DEFAULT '1',
                expires_at TEXT DEFAULT 'Lifetime',
                lifetime INTEGER DEFAULT 1,
                hwid TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                last_ip TEXT DEFAULT '',
                last_login TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(app_id, username),
                FOREIGN KEY (app_id) REFERENCES apps(id) ON DELETE CASCADE
            )
        """)
        
        # 3. Licenses table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id INTEGER NOT NULL,
                license_key TEXT UNIQUE NOT NULL,
                duration_days INTEGER DEFAULT 0,
                level TEXT DEFAULT '1',
                status TEXT DEFAULT 'unused',
                used_by TEXT DEFAULT '',
                used_at TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (app_id) REFERENCES apps(id) ON DELETE CASCADE
            )
        """)
        
        # 4. Variables table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS variables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id INTEGER NOT NULL,
                var_name TEXT NOT NULL,
                var_value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(app_id, var_name),
                FOREIGN KEY (app_id) REFERENCES apps(id) ON DELETE CASCADE
            )
        """)
        
        # 5. Logs table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name TEXT DEFAULT '',
                username TEXT DEFAULT '',
                action TEXT DEFAULT '',
                status TEXT DEFAULT '',
                ip_address TEXT DEFAULT '',
                hwid TEXT DEFAULT '',
                details TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        
        conn.commit()
        
        # Seed default application if not present
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("SELECT id FROM apps WHERE name = ?", ("garaa-App-1",))
        app_row = cur.fetchone()
        if not app_row:
            cur.execute("""
                INSERT INTO apps (name, owner_id, secret, version, announcement, download_url, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "garaa-App-1",
                "garaa",
                "1fb641dc27d1400cd42c88aeae239c74",
                "1.0.0",
                "Welcome to Krishu X Cheats! Cloud Authentication Online.",
                "https://krishu-cheats.com",
                "enabled",
                now_str
            ))
            conn.commit()
            app_id = cur.lastrowid
        else:
            app_id = app_row["id"]
            
        # Seed default user 'garaa' / '123456'
        cur.execute("SELECT id FROM users WHERE app_id = ? AND username = ?", (app_id, "garaa"))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO users (app_id, username, password_hash, level, expires_at, lifetime, hwid, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                app_id,
                "garaa",
                hash_password("123456"),
                "VIP",
                "Lifetime",
                1,
                "",
                "active",
                now_str
            ))
            conn.commit()

        # Seed default user 'admin' / 'admin123'
        cur.execute("SELECT id FROM users WHERE app_id = ? AND username = ?", (app_id, "admin"))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO users (app_id, username, password_hash, level, expires_at, lifetime, hwid, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                app_id,
                "admin",
                hash_password("admin123"),
                "Admin",
                "Lifetime",
                1,
                "",
                "active",
                now_str
            ))
            conn.commit()
            
        # Seed default sample licenses
        sample_keys = [
            ("KXC-LIFE-AAAA-BBBB-CCCC", 0, "VIP"),
            ("KXC-30D-1111-2222-3333", 30, "Premium"),
            ("KXC-7D-4444-5555-6666", 7, "Standard"),
            ("KXC-1D-7777-8888-9999", 1, "Trial")
        ]
        for key, days, lvl in sample_keys:
            cur.execute("SELECT id FROM licenses WHERE license_key = ?", (key,))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO licenses (app_id, license_key, duration_days, level, status, created_at)
                    VALUES (?, ?, ?, ?, 'unused', ?)
                """, (app_id, key, days, lvl, now_str))
        conn.commit()
        
        # Seed default variables
        sample_vars = [
            ("status", "UNDETECTED"),
            ("motd", "Krishu X Cheats - Premium Cloud Protection"),
            ("aimbot_fov", "180"),
            ("bypass_state", "active")
        ]
        for vname, vval in sample_vars:
            cur.execute("SELECT id FROM variables WHERE app_id = ? AND var_name = ?", (app_id, vname))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO variables (app_id, var_name, var_value, created_at)
                    VALUES (?, ?, ?, ?)
                """, (app_id, vname, vval, now_str))
        conn.commit()
        conn.close()

def log_event(app_name, username, action, status, ip, hwid, details=""):
    try:
        with _db_lock:
            conn = get_db()
            conn.execute("""
                INSERT INTO logs (app_name, username, action, status, ip_address, hwid, details, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                app_name or "",
                username or "",
                action or "",
                status or "",
                ip or "",
                hwid or "",
                details or "",
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"[LOG ERROR] {e}")

class KeyAuthHandler(BaseHTTPRequestHandler):
    server_version = "KrishuKeyAuth/1.0.0"

    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, x-api-key, x-owner-id, x-app-name, x-admin-key")

    def _send_json(self, data, status_code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_content, status_code=200):
        body = html_content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors()
        self.end_headers()

    def get_client_ip(self):
        # Support X-Forwarded-For if behind reverse proxy (like Render/Cloudflare)
        xff = self.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        return self.client_address[0] if self.client_address else "127.0.0.1"

    def read_json_body(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                return {}
            raw_data = self.rfile.read(content_length).decode("utf-8")
            if not raw_data:
                return {}
            return json.loads(raw_data)
        except Exception:
            return {}

    def extract_app_auth(self, body):
        name = body.get("name") or self.headers.get("x-app-name") or ""
        owner_id = body.get("ownerid") or body.get("owner_id") or self.headers.get("x-owner-id") or ""
        secret = body.get("secret") or self.headers.get("x-api-key") or ""
        return name.strip(), owner_id.strip(), secret.strip()

    def get_authenticated_app(self, body):
        name, owner_id, secret = self.extract_app_auth(body)
        if not name:
            return None, "Application name is required"
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM apps WHERE name = ?", (name,))
        app = cur.fetchone()
        conn.close()

        if not app:
            return None, f"Application '{name}' not found"

        if secret and app["secret"] != secret:
            return None, "Invalid application secret key"

        if owner_id and app["owner_id"] != owner_id:
            return None, "Invalid application owner ID"

        if app["status"] == "maintenance":
            return None, "Application is currently under scheduled maintenance"

        if app["status"] == "disabled":
            return None, "Application has been disabled by the administrator"

        return app, None

    # =========================================================================
    # ROUTER
    # =========================================================================

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if not path:
            path = "/"

        # 1. Health check
        if path in ("/api/v1/health", "/health"):
            self._send_json({
                "status": "ok",
                "service": "Krishu KeyAuth API",
                "version": "1.0.0",
                "timestamp": datetime.utcnow().isoformat()
            })
            return

        # 2. Get Variable: /api/v1/var/<varName>
        if path.startswith("/api/v1/var/"):
            var_name = unquote(path[len("/api/v1/var/"):])
            self.handle_get_var(var_name)
            return

        # 3. Admin API endpoints
        if path.startswith("/api/v1/admin/"):
            self.handle_admin_get(path, parse_qs(parsed.query))
            return

        # 4. Web Dashboard UI
        if path in ("/", "/admin", "/dashboard"):
            self._send_html(get_dashboard_html())
            return

        # Default 404
        self._send_json({"success": False, "message": "Endpoint not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = self.read_json_body()

        # KeyAuth client endpoints
        if path in ("/api/v1/init", "/init"):
            self.handle_init(body)
        elif path in ("/api/v1/login", "/login"):
            self.handle_login(body)
        elif path in ("/api/v1/register", "/register"):
            self.handle_register(body)
        elif path in ("/api/v1/license", "/license"):
            self.handle_license(body)
        elif path in ("/api/v1/check", "/check"):
            self.handle_check(body)
        elif path in ("/api/v1/hwid-reset", "/hwid-reset"):
            self.handle_hwid_reset(body)
        # Admin API endpoints
        elif path.startswith("/api/v1/admin/"):
            self.handle_admin_post(path, body)
        else:
            self._send_json({"success": False, "message": f"POST endpoint '{path}' not found"}, 404)

    # =========================================================================
    # KEYAUTH CLIENT HANDLERS
    # =========================================================================

    def handle_init(self, body):
        client_ip = self.get_client_ip()
        app, err = self.get_authenticated_app(body)
        if err or not app:
            log_event(body.get("name"), "", "INIT", "FAILED", client_ip, "", err)
            self._send_json({
                "success": False,
                "message": err or "Initialization failed"
            }, 200)
            return

        client_version = body.get("version", "1.0.0")
        log_event(app["name"], "", "INIT", "SUCCESS", client_ip, "", f"Client v{client_version}")

        self._send_json({
            "success": True,
            "message": "Initialized successfully",
            "name": app["name"],
            "version": app["version"],
            "announcement": app["announcement"] or "Welcome to Krishu X Cheats!",
            "downloadUrl": app["download_url"] or ""
        })

    def handle_login(self, body):
        client_ip = self.get_client_ip()
        app, err = self.get_authenticated_app(body)
        if err or not app:
            log_event(body.get("name"), body.get("username"), "LOGIN", "FAILED", client_ip, body.get("hwid"), err)
            self._send_json({"success": False, "message": err or "Authentication error"}, 200)
            return

        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        hwid = (body.get("hwid") or "").strip()

        if not username or not password:
            self._send_json({"success": False, "message": "Username and password are required"}, 200)
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE app_id = ? AND username = ?", (app["id"], username))
        user = cur.fetchone()

        if not user or user["password_hash"] != hash_password(password):
            conn.close()
            log_event(app["name"], username, "LOGIN", "FAILED", client_ip, hwid, "Invalid credentials")
            self._send_json({"success": False, "message": "Invalid username or password"}, 200)
            return

        if user["status"] == "banned":
            conn.close()
            log_event(app["name"], username, "LOGIN", "BANNED", client_ip, hwid, "Banned account tried login")
            self._send_json({"success": False, "message": "Account has been suspended or banned"}, 200)
            return

        # Check expiration
        is_lifetime = bool(user["lifetime"] or str(user["expires_at"]).lower() == "lifetime")
        if not is_lifetime and user["expires_at"]:
            try:
                exp_date = datetime.strptime(user["expires_at"], "%Y-%m-%d %H:%M:%S")
                if datetime.utcnow() > exp_date:
                    conn.close()
                    log_event(app["name"], username, "LOGIN", "EXPIRED", client_ip, hwid, "Subscription expired")
                    self._send_json({"success": False, "message": "Your subscription has expired"}, 200)
                    return
            except Exception:
                pass

        # Check / bind HWID
        user_hwid = user["hwid"] or ""
        if not user_hwid:
            # First login: Auto-bind HWID
            user_hwid = hwid
            cur.execute("UPDATE users SET hwid = ? WHERE id = ?", (hwid, user["id"]))
            conn.commit()
        elif hwid and user_hwid != hwid:
            conn.close()
            log_event(app["name"], username, "LOGIN", "HWID_MISMATCH", client_ip, hwid, f"Stored: {user_hwid}")
            self._send_json({
                "success": False,
                "message": "HWID mismatch. Please request an HWID reset from your admin."
            }, 200)
            return

        # Update last login info
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE users SET last_login = ?, last_ip = ? WHERE id = ?", (now_str, client_ip, user["id"]))
        conn.commit()
        conn.close()

        token = secrets.token_hex(20)
        log_event(app["name"], username, "LOGIN", "SUCCESS", client_ip, hwid, f"Role: {user['level']}")

        self._send_json({
            "success": True,
            "message": "Login successful",
            "username": user["username"],
            "level": str(user["level"] or "1"),
            "expiresAt": "Lifetime" if is_lifetime else str(user["expires_at"]),
            "lifetime": is_lifetime,
            "hwid": user_hwid,
            "token": token
        })

    def handle_register(self, body):
        client_ip = self.get_client_ip()
        app, err = self.get_authenticated_app(body)
        if err or not app:
            self._send_json({"success": False, "message": err or "Authentication error"}, 200)
            return

        username = (body.get("username") or "").strip()
        password = body.get("password") or ""
        license_key = (body.get("licenseKey") or body.get("key") or "").strip()
        hwid = (body.get("hwid") or "").strip()

        if not username or not password or not license_key:
            self._send_json({"success": False, "message": "Username, password, and license key are required"}, 200)
            return

        conn = get_db()
        cur = conn.cursor()

        # Check existing user
        cur.execute("SELECT id FROM users WHERE app_id = ? AND username = ?", (app["id"], username))
        if cur.fetchone():
            conn.close()
            self._send_json({"success": False, "message": "Username already exists"}, 200)
            return

        # Check license key
        cur.execute("SELECT * FROM licenses WHERE app_id = ? AND license_key = ?", (app["id"], license_key))
        license_row = cur.fetchone()
        if not license_row:
            conn.close()
            self._send_json({"success": False, "message": "Invalid license key"}, 200)
            return

        if license_row["status"] != "unused":
            conn.close()
            self._send_json({"success": False, "message": f"License key is already {license_row['status']}"}, 200)
            return

        # Calculate expiration
        duration_days = license_row["duration_days"]
        if duration_days <= 0:
            expires_at = "Lifetime"
            lifetime = 1
        else:
            expires_at = (datetime.utcnow() + timedelta(days=duration_days)).strftime("%Y-%m-%d %H:%M:%S")
            lifetime = 0

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # Insert user
        cur.execute("""
            INSERT INTO users (app_id, username, password_hash, level, expires_at, lifetime, hwid, status, last_ip, last_login, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """, (
            app["id"], username, hash_password(password), license_row["level"],
            expires_at, lifetime, hwid, client_ip, now_str, now_str
        ))

        # Mark license used
        cur.execute("""
            UPDATE licenses SET status = 'used', used_by = ?, used_at = ? WHERE id = ?
        """, (username, now_str, license_row["id"]))

        conn.commit()
        conn.close()

        token = secrets.token_hex(20)
        log_event(app["name"], username, "REGISTER", "SUCCESS", client_ip, hwid, f"Key: {license_key}")

        self._send_json({
            "success": True,
            "message": "Registration successful",
            "username": username,
            "level": license_row["level"],
            "expiresAt": expires_at,
            "token": token
        })

    def handle_license(self, body):
        client_ip = self.get_client_ip()
        app, err = self.get_authenticated_app(body)
        if err or not app:
            self._send_json({"success": False, "message": err or "Authentication error"}, 200)
            return

        license_key = (body.get("key") or body.get("licenseKey") or "").strip()
        hwid = (body.get("hwid") or "").strip()

        if not license_key:
            self._send_json({"success": False, "message": "License key is required"}, 200)
            return

        conn = get_db()
        cur = conn.cursor()

        # Check if license exists as a user (direct key auth mode)
        cur.execute("SELECT * FROM users WHERE app_id = ? AND username = ?", (app["id"], license_key))
        user = cur.fetchone()

        if user:
            # Login existing key-user
            is_lifetime = bool(user["lifetime"] or str(user["expires_at"]).lower() == "lifetime")
            user_hwid = user["hwid"] or ""
            if not user_hwid:
                user_hwid = hwid
                cur.execute("UPDATE users SET hwid = ? WHERE id = ?", (hwid, user["id"]))
                conn.commit()
            elif hwid and user_hwid != hwid:
                conn.close()
                self._send_json({"success": False, "message": "HWID mismatch on this license"}, 200)
                return

            token = secrets.token_hex(20)
            conn.close()
            log_event(app["name"], license_key, "LICENSE_LOGIN", "SUCCESS", client_ip, hwid, "Direct key login")

            self._send_json({
                "success": True,
                "message": "License verified",
                "username": license_key,
                "level": user["level"],
                "expiresAt": "Lifetime" if is_lifetime else user["expires_at"],
                "lifetime": is_lifetime,
                "token": token
            })
            return

        # Otherwise check licenses table
        cur.execute("SELECT * FROM licenses WHERE app_id = ? AND license_key = ?", (app["id"], license_key))
        license_row = cur.fetchone()

        if not license_row:
            conn.close()
            self._send_json({"success": False, "message": "Invalid license key"}, 200)
            return

        if license_row["status"] != "unused":
            conn.close()
            self._send_json({"success": False, "message": f"License key is already {license_row['status']}"}, 200)
            return

        # Activate key as new user account
        duration_days = license_row["duration_days"]
        if duration_days <= 0:
            expires_at = "Lifetime"
            lifetime = 1
        else:
            expires_at = (datetime.utcnow() + timedelta(days=duration_days)).strftime("%Y-%m-%d %H:%M:%S")
            lifetime = 0

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO users (app_id, username, password_hash, level, expires_at, lifetime, hwid, status, last_ip, last_login, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """, (
            app["id"], license_key, hash_password(license_key), license_row["level"],
            expires_at, lifetime, hwid, client_ip, now_str, now_str
        ))
        cur.execute("UPDATE licenses SET status = 'used', used_by = ?, used_at = ? WHERE id = ?", (license_key, now_str, license_row["id"]))
        conn.commit()
        conn.close()

        token = secrets.token_hex(20)
        log_event(app["name"], license_key, "LICENSE_ACTIVATE", "SUCCESS", client_ip, hwid, "First activation")

        self._send_json({
            "success": True,
            "message": "License activated successfully",
            "username": license_key,
            "level": license_row["level"],
            "expiresAt": expires_at,
            "lifetime": lifetime == 1,
            "token": token
        })

    def handle_get_var(self, var_name):
        # Extract headers or query params
        app_name = self.headers.get("x-app-name") or "garaa-App-1"
        secret = self.headers.get("x-api-key")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, secret FROM apps WHERE name = ?", (app_name,))
        app = cur.fetchone()

        if not app:
            conn.close()
            self._send_json({"success": False, "value": ""}, 200)
            return

        if secret and app["secret"] != secret:
            conn.close()
            self._send_json({"success": False, "value": ""}, 200)
            return

        cur.execute("SELECT var_value FROM variables WHERE app_id = ? AND var_name = ?", (app["id"], var_name))
        row = cur.fetchone()
        conn.close()

        if row:
            self._send_json({"success": True, "value": row["var_value"]})
        else:
            self._send_json({"success": False, "value": ""})

    def handle_check(self, body):
        self._send_json({"success": True, "message": "Session valid and server online"})

    def handle_hwid_reset(self, body):
        username = (body.get("username") or "").strip()
        app, err = self.get_authenticated_app(body)
        if err or not app or not username:
            self._send_json({"success": False, "message": "Invalid request"}, 200)
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE users SET hwid = '' WHERE app_id = ? AND username = ?", (app["id"], username))
        conn.commit()
        conn.close()

        self._send_json({"success": True, "message": "HWID reset successfully. You can now login on your new PC."})

    # =========================================================================
    # ADMIN API HANDLERS (FOR DASHBOARD)
    # =========================================================================

    def handle_admin_get(self, path, query):
        conn = get_db()
        cur = conn.cursor()

        if path == "/api/v1/admin/stats":
            cur.execute("SELECT COUNT(*) as total FROM users")
            total_users = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) as total FROM licenses WHERE status = 'unused'")
            unused_licenses = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) as total FROM licenses WHERE status = 'used'")
            used_licenses = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) as total FROM apps")
            total_apps = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) as total FROM logs")
            total_logs = cur.fetchone()["total"]
            conn.close()

            self._send_json({
                "success": True,
                "stats": {
                    "totalUsers": total_users,
                    "unusedLicenses": unused_licenses,
                    "usedLicenses": used_licenses,
                    "totalApps": total_apps,
                    "totalLogs": total_logs
                }
            })
            return

        if path == "/api/v1/admin/users":
            cur.execute("""
                SELECT u.id, u.username, u.level, u.expires_at, u.lifetime, u.hwid, u.status, u.last_ip, u.last_login, u.created_at, a.name as app_name
                FROM users u
                JOIN apps a ON u.app_id = a.id
                ORDER BY u.id DESC
            """)
            users = [dict(row) for row in cur.fetchall()]
            conn.close()
            self._send_json({"success": True, "users": users})
            return

        if path == "/api/v1/admin/licenses":
            cur.execute("""
                SELECT l.id, l.license_key, l.duration_days, l.level, l.status, l.used_by, l.used_at, l.created_at, a.name as app_name
                FROM licenses l
                JOIN apps a ON l.app_id = a.id
                ORDER BY l.id DESC
            """)
            licenses = [dict(row) for row in cur.fetchall()]
            conn.close()
            self._send_json({"success": True, "licenses": licenses})
            return

        if path == "/api/v1/admin/apps":
            cur.execute("SELECT * FROM apps ORDER BY id ASC")
            apps = [dict(row) for row in cur.fetchall()]
            conn.close()
            self._send_json({"success": True, "apps": apps})
            return

        if path == "/api/v1/admin/vars":
            cur.execute("""
                SELECT v.id, v.var_name, v.var_value, v.created_at, a.name as app_name
                FROM variables v
                JOIN apps a ON v.app_id = a.id
                ORDER BY v.id DESC
            """)
            variables = [dict(row) for row in cur.fetchall()]
            conn.close()
            self._send_json({"success": True, "variables": variables})
            return

        if path == "/api/v1/admin/logs":
            cur.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 100")
            logs = [dict(row) for row in cur.fetchall()]
            conn.close()
            self._send_json({"success": True, "logs": logs})
            return

        conn.close()
        self._send_json({"success": False, "message": "Unknown admin endpoint"}, 404)

    def handle_admin_post(self, path, body):
        conn = get_db()
        cur = conn.cursor()
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Add user
        if path == "/api/v1/admin/users/create":
            app_id = body.get("app_id", 1)
            username = (body.get("username") or "").strip()
            password = body.get("password") or "123456"
            level = body.get("level", "1")
            duration_days = int(body.get("duration_days", 0))

            if not username:
                self._send_json({"success": False, "message": "Username is required"}, 400)
                conn.close()
                return

            if duration_days <= 0:
                expires_at = "Lifetime"
                lifetime = 1
            else:
                expires_at = (datetime.utcnow() + timedelta(days=duration_days)).strftime("%Y-%m-%d %H:%M:%S")
                lifetime = 0

            try:
                cur.execute("""
                    INSERT INTO users (app_id, username, password_hash, level, expires_at, lifetime, hwid, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, '', 'active', ?)
                """, (app_id, username, hash_password(password), level, expires_at, lifetime, now_str))
                conn.commit()
                conn.close()
                self._send_json({"success": True, "message": f"User '{username}' created successfully"})
            except sqlite3.IntegrityError:
                conn.close()
                self._send_json({"success": False, "message": "Username already exists"}, 400)
            return

        # 2. Reset user HWID
        if path == "/api/v1/admin/users/reset-hwid":
            user_id = body.get("user_id")
            cur.execute("UPDATE users SET hwid = '' WHERE id = ?", (user_id,))
            conn.commit()
            conn.close()
            self._send_json({"success": True, "message": "User HWID reset successfully"})
            return

        # 3. Toggle ban user
        if path == "/api/v1/admin/users/toggle-ban":
            user_id = body.get("user_id")
            cur.execute("SELECT status FROM users WHERE id = ?", (user_id,))
            user = cur.fetchone()
            if user:
                new_status = "banned" if user["status"] == "active" else "active"
                cur.execute("UPDATE users SET status = ? WHERE id = ?", (new_status, user_id))
                conn.commit()
                conn.close()
                self._send_json({"success": True, "message": f"User status set to {new_status}"})
            else:
                conn.close()
                self._send_json({"success": False, "message": "User not found"}, 404)
            return

        # 4. Delete user
        if path == "/api/v1/admin/users/delete":
            user_id = body.get("user_id")
            cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            conn.close()
            self._send_json({"success": True, "message": "User deleted successfully"})
            return

        # 5. Generate Licenses
        if path == "/api/v1/admin/licenses/generate":
            app_id = body.get("app_id", 1)
            prefix = (body.get("prefix") or "KXC").upper().strip()
            count = min(max(int(body.get("count", 1)), 1), 50)
            duration_days = int(body.get("duration_days", 30))
            level = body.get("level", "1")

            generated = []
            for _ in range(count):
                p1 = secrets.token_hex(2).upper()
                p2 = secrets.token_hex(2).upper()
                p3 = secrets.token_hex(2).upper()
                key = f"{prefix}-{p1}-{p2}-{p3}"
                cur.execute("""
                    INSERT INTO licenses (app_id, license_key, duration_days, level, status, created_at)
                    VALUES (?, ?, ?, ?, 'unused', ?)
                """, (app_id, key, duration_days, level, now_str))
                generated.append(key)

            conn.commit()
            conn.close()
            self._send_json({
                "success": True,
                "message": f"Generated {count} license key(s)",
                "keys": generated
            })
            return

        # 6. Delete license
        if path == "/api/v1/admin/licenses/delete":
            license_id = body.get("license_id")
            cur.execute("DELETE FROM licenses WHERE id = ?", (license_id,))
            conn.commit()
            conn.close()
            self._send_json({"success": True, "message": "License deleted"})
            return

        # 7. Update App
        if path == "/api/v1/admin/apps/update":
            app_id = body.get("id")
            version = body.get("version", "1.0.0")
            announcement = body.get("announcement", "")
            download_url = body.get("download_url", "")
            status = body.get("status", "enabled")
            secret = body.get("secret")

            if secret:
                cur.execute("""
                    UPDATE apps SET version = ?, announcement = ?, download_url = ?, status = ?, secret = ?
                    WHERE id = ?
                """, (version, announcement, download_url, status, secret, app_id))
            else:
                cur.execute("""
                    UPDATE apps SET version = ?, announcement = ?, download_url = ?, status = ?
                    WHERE id = ?
                """, (version, announcement, download_url, status, app_id))

            conn.commit()
            conn.close()
            self._send_json({"success": True, "message": "Application configuration updated"})
            return

        # 8. Set/Update variable
        if path == "/api/v1/admin/vars/save":
            app_id = body.get("app_id", 1)
            var_name = (body.get("var_name") or "").strip()
            var_value = body.get("var_value", "")

            if not var_name:
                self._send_json({"success": False, "message": "Variable name is required"}, 400)
                conn.close()
                return

            cur.execute("""
                INSERT INTO variables (app_id, var_name, var_value, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(app_id, var_name) DO UPDATE SET var_value = excluded.var_value
            """, (app_id, var_name, var_value, now_str))
            conn.commit()
            conn.close()
            self._send_json({"success": True, "message": f"Variable '{var_name}' saved"})
            return

        # 9. Delete variable
        if path == "/api/v1/admin/vars/delete":
            var_id = body.get("var_id")
            cur.execute("DELETE FROM variables WHERE id = ?", (var_id,))
            conn.commit()
            conn.close()
            self._send_json({"success": True, "message": "Variable deleted"})
            return

        conn.close()
        self._send_json({"success": False, "message": "Unknown action"}, 404)

# =============================================================================
# ADMIN DASHBOARD HTML & CSS (EMBEDDED)
# =============================================================================

def get_dashboard_html():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Krishu KeyAuth &mdash; Cloud API Web Panel</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #090a0f;
      --bg-card: #12141f;
      --bg-card-hover: #171a29;
      --bg-input: #0c0e16;
      --border: rgba(255, 255, 255, 0.08);
      --border-focus: rgba(235, 47, 47, 0.5);
      --crimson: #eb2f2f;
      --crimson-glow: rgba(235, 47, 47, 0.35);
      --crimson-hover: #ff4747;
      --text: #f0f2f8;
      --text-muted: #8b92a8;
      --text-dim: #545b73;
      --success: #10b981;
      --success-glow: rgba(16, 185, 129, 0.2);
      --warning: #f59e0b;
      --danger: #ef4444;
      --radius: 12px;
      --font-main: 'Outfit', -apple-system, sans-serif;
      --font-code: 'JetBrains Mono', monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: radial-gradient(circle at 15% 15%, #180d16 0%, var(--bg-dark) 55%), #090a0f;
      color: var(--text);
      font-family: var(--font-main);
      min-height: 100vh;
      display: flex;
    }

    /* Sidebar */
    .sidebar {
      width: 260px;
      background: rgba(14, 16, 25, 0.95);
      backdrop-filter: blur(20px);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      position: fixed;
      top: 0; bottom: 0; left: 0;
      z-index: 100;
    }

    .brand {
      padding: 24px 20px;
      display: flex;
      align-items: center;
      gap: 12px;
      border-bottom: 1px solid var(--border);
    }
    .brand-icon {
      width: 42px; height: 42px;
      background: linear-gradient(135deg, var(--crimson), #800b1b);
      border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
      font-size: 22px; font-weight: 800;
      box-shadow: 0 4px 15px var(--crimson-glow);
    }
    .brand-text h1 { font-size: 16px; font-weight: 700; letter-spacing: 0.5px; }
    .brand-text p { font-size: 11px; color: var(--crimson); font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }

    .nav-list { list-style: none; padding: 16px 12px; flex: 1; }
    .nav-item { margin-bottom: 6px; }
    .nav-link {
      display: flex; align-items: center; gap: 12px;
      padding: 12px 14px;
      color: var(--text-muted);
      text-decoration: none;
      border-radius: 8px;
      font-size: 14px; font-weight: 500;
      transition: all 0.2s ease;
      cursor: pointer;
    }
    .nav-link:hover { color: var(--text); background: rgba(255,255,255,0.04); }
    .nav-link.active {
      color: #fff;
      background: linear-gradient(90deg, rgba(235, 47, 47, 0.25), rgba(235, 47, 47, 0.05));
      border-left: 3px solid var(--crimson);
      box-shadow: inset 0 0 15px rgba(235, 47, 47, 0.1);
    }
    .nav-link svg { width: 18px; height: 18px; opacity: 0.8; }

    .sidebar-footer {
      padding: 16px;
      border-top: 1px solid var(--border);
      font-size: 12px;
      color: var(--text-dim);
    }
    .status-badge {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 4px 10px;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 20px;
      color: var(--success);
      font-weight: 600; font-size: 11px;
    }
    .status-dot { width: 6px; height: 6px; background: var(--success); border-radius: 50%; box-shadow: 0 0 8px var(--success); }

    /* Main Content */
    .main {
      margin-left: 260px;
      flex: 1;
      padding: 32px 40px;
      max-width: 1400px;
    }

    .header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 28px;
    }
    .page-title h2 { font-size: 24px; font-weight: 700; margin-bottom: 4px; }
    .page-title p { color: var(--text-muted); font-size: 14px; }

    /* Top Stats */
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 18px;
      margin-bottom: 32px;
    }
    .stat-card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px;
      display: flex; align-items: center; justify-content: space-between;
      transition: transform 0.2s, border-color 0.2s;
    }
    .stat-card:hover { transform: translateY(-2px); border-color: rgba(255,255,255,0.15); }
    .stat-info h3 { font-size: 26px; font-weight: 800; margin-bottom: 4px; }
    .stat-info span { font-size: 13px; color: var(--text-muted); font-weight: 500; }
    .stat-icon {
      width: 46px; height: 46px;
      border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
      background: rgba(255, 255, 255, 0.05);
      color: var(--crimson);
    }

    /* Content Cards */
    .card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 24px;
      margin-bottom: 28px;
    }
    .card-header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 20px;
    }
    .card-header h3 { font-size: 18px; font-weight: 600; }

    /* Buttons */
    .btn {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 9px 18px;
      border-radius: 8px;
      font-size: 13px; font-weight: 600;
      cursor: pointer;
      border: none;
      transition: all 0.2s;
      text-decoration: none;
      font-family: var(--font-main);
    }
    .btn-primary {
      background: linear-gradient(135deg, var(--crimson), #c41c1c);
      color: #fff;
      box-shadow: 0 4px 12px var(--crimson-glow);
    }
    .btn-primary:hover { background: linear-gradient(135deg, var(--crimson-hover), #e62020); transform: translateY(-1px); }
    .btn-secondary {
      background: rgba(255, 255, 255, 0.08);
      color: var(--text);
    }
    .btn-secondary:hover { background: rgba(255, 255, 255, 0.12); }
    .btn-sm { padding: 6px 12px; font-size: 12px; border-radius: 6px; }
    .btn-danger { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .btn-danger:hover { background: rgba(239, 68, 68, 0.3); }

    /* Tables */
    .table-container {
      overflow-x: auto;
    }
    table {
      width: 100%; border-collapse: collapse; text-align: left; font-size: 13px;
    }
    th {
      padding: 12px 14px;
      color: var(--text-dim);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 11px;
      letter-spacing: 0.5px;
      border-bottom: 1px solid var(--border);
    }
    td {
      padding: 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      color: var(--text);
    }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }

    .tag {
      display: inline-block;
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 11px; font-weight: 600;
    }
    .tag-active { background: rgba(16, 185, 129, 0.15); color: #34d399; }
    .tag-unused { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
    .tag-used { background: rgba(255, 255, 255, 0.08); color: var(--text-muted); }
    .tag-banned { background: rgba(239, 68, 68, 0.15); color: #f87171; }
    .code-text { font-family: var(--font-code); color: #ff7b72; font-size: 12px; }

    /* Modals */
    .modal-backdrop {
      display: none;
      position: fixed; top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(6px);
      z-index: 999;
      align-items: center; justify-content: center;
    }
    .modal-backdrop.show { display: flex; }
    .modal {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      width: 90%; max-width: 480px;
      padding: 28px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
      animation: modalIn 0.2s ease-out;
    }
    @keyframes modalIn {
      from { transform: scale(0.95); opacity: 0; }
      to { transform: scale(1); opacity: 1; }
    }
    .modal-title { font-size: 18px; font-weight: 700; margin-bottom: 18px; }

    .form-group { margin-bottom: 16px; }
    .form-group label { display: block; font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px; }
    .form-control {
      width: 100%;
      background: var(--bg-input);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 14px;
      color: var(--text);
      font-size: 13px;
      font-family: inherit;
      outline: none;
      transition: border-color 0.2s;
    }
    .form-control:focus { border-color: var(--border-focus); box-shadow: 0 0 10px var(--crimson-glow); }
    .modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 24px; }

    /* Tab contents */
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }
  </style>
</head>
<body>
  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-icon">K</div>
      <div class="brand-text">
        <h1>Krishu KeyAuth</h1>
        <p>API v1 Server</p>
      </div>
    </div>
    <ul class="nav-list">
      <li class="nav-item"><a class="nav-link active" onclick="switchTab('dashboard')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/></svg>
        Dashboard
      </a></li>
      <li class="nav-item"><a class="nav-link" onclick="switchTab('users')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
        Users
      </a></li>
      <li class="nav-item"><a class="nav-link" onclick="switchTab('licenses')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        Licenses / Keys
      </a></li>
      <li class="nav-item"><a class="nav-link" onclick="switchTab('apps')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
        Application Config
      </a></li>
      <li class="nav-item"><a class="nav-link" onclick="switchTab('vars')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7V4h16v3M9 20h6M12 4v16"/></svg>
        App Variables
      </a></li>
      <li class="nav-item"><a class="nav-link" onclick="switchTab('logs')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
        Activity Logs
      </a></li>
      <li class="nav-item"><a class="nav-link" onclick="switchTab('setup')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
        C# Client & Setup
      </a></li>
    </ul>
    <div class="sidebar-footer">
      <div class="status-badge"><span class="status-dot"></span> API Online (v1)</div>
      <p style="margin-top: 8px;">Port: <b id="portDisplay">5000</b></p>
    </div>
  </aside>

  <!-- Main Content Area -->
  <main class="main">
    <!-- Header -->
    <div class="header">
      <div class="page-title">
        <h2 id="viewTitle">Overview Dashboard</h2>
        <p>Live management console for Krishu X Cheats / KeyAuth</p>
      </div>
      <div>
        <button class="btn btn-primary" onclick="openGenerateModal()">+ Generate Keys</button>
      </div>
    </div>

    <!-- Stats Row -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-info">
          <h3 id="statUsers">0</h3>
          <span>Registered Users</span>
        </div>
        <div class="stat-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-info">
          <h3 id="statUnusedKeys">0</h3>
          <span>Unused Licenses</span>
        </div>
        <div class="stat-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-info">
          <h3 id="statUsedKeys">0</h3>
          <span>Redeemed Keys</span>
        </div>
        <div class="stat-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-info">
          <h3 id="statLogs">0</h3>
          <span>Audit Log Events</span>
        </div>
        <div class="stat-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 14 14"/></svg>
        </div>
      </div>
    </div>

    <!-- TAB: DASHBOARD -->
    <div id="tab-dashboard" class="tab-pane active">
      <div class="card">
        <div class="card-header">
          <h3>Quick Overview &mdash; Active App: garaa-App-1</h3>
          <span class="status-badge"><span class="status-dot"></span> Ready For C# Panel</span>
        </div>
        <p style="color: var(--text-muted); font-size: 14px; line-height: 1.6;">
          Backend API ini 100% kompatibel langsung dengan C# SDK di <code>krishuxcheats.cs</code> dan Form1.cs milik Krishu X Cheats.
          Endpoint aktif: <code>/api/v1/init</code>, <code>/api/v1/login</code>, <code>/api/v1/register</code>, <code>/api/v1/license</code>, dan <code>/api/v1/var/:name</code>.
        </p>
      </div>

      <div class="card">
        <div class="card-header">
          <h3>Recent Users</h3>
          <button class="btn btn-secondary btn-sm" onclick="switchTab('users')">View All</button>
        </div>
        <div class="table-container">
          <table id="recentUsersTable">
            <thead>
              <tr>
                <th>Username</th>
                <th>Level</th>
                <th>Expires</th>
                <th>HWID Status</th>
                <th>Last Login</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB: USERS -->
    <div id="tab-users" class="tab-pane">
      <div class="card">
        <div class="card-header">
          <h3>Users List</h3>
          <button class="btn btn-primary btn-sm" onclick="openAddUserModal()">+ Add User</button>
        </div>
        <div class="table-container">
          <table id="usersTable">
            <thead>
              <tr>
                <th>ID</th>
                <th>Username</th>
                <th>Level</th>
                <th>Expires</th>
                <th>HWID</th>
                <th>Status</th>
                <th>Last IP</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB: LICENSES -->
    <div id="tab-licenses" class="tab-pane">
      <div class="card">
        <div class="card-header">
          <h3>Licenses / Keys</h3>
          <button class="btn btn-primary btn-sm" onclick="openGenerateModal()">+ Generate Keys</button>
        </div>
        <div class="table-container">
          <table id="licensesTable">
            <thead>
              <tr>
                <th>License Key</th>
                <th>Duration</th>
                <th>Level</th>
                <th>Status</th>
                <th>Used By</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB: APPS -->
    <div id="tab-apps" class="tab-pane">
      <div class="card">
        <div class="card-header">
          <h3>Application Configuration</h3>
          <button class="btn btn-primary btn-sm" onclick="saveAppConfig()">Save Changes</button>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
          <div class="form-group">
            <label>App Name</label>
            <input type="text" id="cfgAppName" class="form-control" readonly>
          </div>
          <div class="form-group">
            <label>Owner ID</label>
            <input type="text" id="cfgOwnerId" class="form-control" readonly>
          </div>
          <div class="form-group">
            <label>App Secret (x-api-key)</label>
            <input type="text" id="cfgSecret" class="form-control">
          </div>
          <div class="form-group">
            <label>Version</label>
            <input type="text" id="cfgVersion" class="form-control">
          </div>
          <div class="form-group" style="grid-column: span 2;">
            <label>Announcement Message</label>
            <input type="text" id="cfgAnnouncement" class="form-control">
          </div>
          <div class="form-group" style="grid-column: span 2;">
            <label>Download URL</label>
            <input type="text" id="cfgDownloadUrl" class="form-control">
          </div>
        </div>
      </div>
    </div>

    <!-- TAB: VARS -->
    <div id="tab-vars" class="tab-pane">
      <div class="card">
        <div class="card-header">
          <h3>App Variables (GET /api/v1/var/:name)</h3>
          <button class="btn btn-primary btn-sm" onclick="openAddVarModal()">+ Add Variable</button>
        </div>
        <div class="table-container">
          <table id="varsTable">
            <thead>
              <tr>
                <th>Variable Name</th>
                <th>Value</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB: LOGS -->
    <div id="tab-logs" class="tab-pane">
      <div class="card">
        <div class="card-header">
          <h3>Audit & Auth Logs (Last 100)</h3>
          <button class="btn btn-secondary btn-sm" onclick="loadLogs()">Refresh</button>
        </div>
        <div class="table-container">
          <table id="logsTable">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Action</th>
                <th>Username</th>
                <th>Status</th>
                <th>IP Address</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB: SETUP -->
    <div id="tab-setup" class="tab-pane">
      <div class="card">
        <div class="card-header">
          <h3>How to Connect with Form1.cs</h3>
        </div>
        <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 16px;">
          Ganti <code>apiUrl</code> di <b>Form1.cs</b> line 92 dengan URL server Anda:
        </p>
        <pre style="background: #08090d; padding: 18px; border-radius: 8px; border: 1px solid var(--border); font-family: var(--font-code); font-size: 13px; color: #a5d6ff; overflow-x: auto;">
public static KrishuXCheats.api KeyAuthApp = new KrishuXCheats.api(
    name: "garaa-App-1",
    ownerid: "garaa",
    secret: "1fb641dc27d1400cd42c88aeae239c74",
    version: "1.0.0",
    apiUrl: "<span style="color: #7ee787;">http://localhost:5000/api/v1</span>" // ATAU URL Render Anda
);</pre>
      </div>

      <div class="card">
        <div class="card-header">
          <h3>Default Pre-Configured Accounts</h3>
        </div>
        <ul style="color: var(--text-muted); font-size: 14px; line-height: 2; margin-left: 20px;">
          <li>Default User: <code>garaa</code> / Password: <code>123456</code> (Lifetime access)</li>
          <li>Default Admin: <code>admin</code> / Password: <code>admin123</code> (Lifetime access)</li>
          <li>Default App Secret: <code>1fb641dc27d1400cd42c88aeae239c74</code></li>
        </ul>
      </div>
    </div>
  </main>

  <!-- MODAL: ADD USER -->
  <div id="modalAddUser" class="modal-backdrop">
    <div class="modal">
      <div class="modal-title">Create New User</div>
      <div class="form-group">
        <label>Username</label>
        <input type="text" id="newUsername" class="form-control" placeholder="e.g. player1">
      </div>
      <div class="form-group">
        <label>Password</label>
        <input type="password" id="newPassword" class="form-control" placeholder="Password">
      </div>
      <div class="form-group">
        <label>Level</label>
        <select id="newLevel" class="form-control">
          <option value="1">1 (Standard)</option>
          <option value="VIP">VIP</option>
          <option value="Admin">Admin</option>
        </select>
      </div>
      <div class="form-group">
        <label>Duration</label>
        <select id="newDuration" class="form-control">
          <option value="0">Lifetime</option>
          <option value="1">1 Day</option>
          <option value="7">7 Days</option>
          <option value="30">30 Days</option>
          <option value="365">1 Year</option>
        </select>
      </div>
      <div class="modal-actions">
        <button class="btn btn-secondary" onclick="closeModal('modalAddUser')">Cancel</button>
        <button class="btn btn-primary" onclick="submitAddUser()">Create User</button>
      </div>
    </div>
  </div>

  <!-- MODAL: GENERATE KEYS -->
  <div id="modalGenerate" class="modal-backdrop">
    <div class="modal">
      <div class="modal-title">Generate License Keys</div>
      <div class="form-group">
        <label>Key Prefix</label>
        <input type="text" id="genPrefix" class="form-control" value="KXC">
      </div>
      <div class="form-group">
        <label>Amount of Keys</label>
        <input type="number" id="genCount" class="form-control" value="5" min="1" max="50">
      </div>
      <div class="form-group">
        <label>Subscription Duration</label>
        <select id="genDuration" class="form-control">
          <option value="0">Lifetime (No Expiry)</option>
          <option value="1">1 Day</option>
          <option value="7">7 Days</option>
          <option value="30" selected>30 Days</option>
          <option value="90">90 Days</option>
        </select>
      </div>
      <div class="form-group">
        <label>Level</label>
        <select id="genLevel" class="form-control">
          <option value="1">1 (Standard)</option>
          <option value="VIP" selected>VIP</option>
        </select>
      </div>
      <div class="modal-actions">
        <button class="btn btn-secondary" onclick="closeModal('modalGenerate')">Cancel</button>
        <button class="btn btn-primary" onclick="submitGenerate()">Generate</button>
      </div>
    </div>
  </div>

  <!-- MODAL: ADD VAR -->
  <div id="modalAddVar" class="modal-backdrop">
    <div class="modal">
      <div class="modal-title">Add / Edit App Variable</div>
      <div class="form-group">
        <label>Variable Name</label>
        <input type="text" id="newVarName" class="form-control" placeholder="e.g. cheat_status">
      </div>
      <div class="form-group">
        <label>Variable Value</label>
        <input type="text" id="newVarValue" class="form-control" placeholder="e.g. UNDETECTED">
      </div>
      <div class="modal-actions">
        <button class="btn btn-secondary" onclick="closeModal('modalAddVar')">Cancel</button>
        <button class="btn btn-primary" onclick="submitAddVar()">Save</button>
      </div>
    </div>
  </div>

  <script>
    let currentAppId = 1;

    function switchTab(tabName) {
      document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-link').forEach(el => el.classList.remove('active'));
      
      const tab = document.getElementById('tab-' + tabName);
      if (tab) tab.classList.add('active');

      const titles = {
        'dashboard': 'Overview Dashboard',
        'users': 'User Management',
        'licenses': 'License Keys Management',
        'apps': 'Application Settings',
        'vars': 'Global App Variables',
        'logs': 'Audit & Auth Logs',
        'setup': 'C# Client & Deployment Guide'
      };
      document.getElementById('viewTitle').innerText = titles[tabName] || 'Dashboard';
      
      // Update sidebar nav active state
      const links = document.querySelectorAll('.nav-link');
      links.forEach(l => {
        if (l.getAttribute('onclick') && l.getAttribute('onclick').includes(tabName)) {
          l.classList.add('active');
        }
      });

      if (tabName === 'dashboard') loadDashboard();
      if (tabName === 'users') loadUsers();
      if (tabName === 'licenses') loadLicenses();
      if (tabName === 'apps') loadApps();
      if (tabName === 'vars') loadVars();
      if (tabName === 'logs') loadLogs();
    }

    function openModal(id) { document.getElementById(id).classList.add('show'); }
    function closeModal(id) { document.getElementById(id).classList.remove('show'); }
    function openAddUserModal() { openModal('modalAddUser'); }
    function openGenerateModal() { openModal('modalGenerate'); }
    function openAddVarModal() { openModal('modalAddVar'); }

    async function loadDashboard() {
      try {
        const res = await fetch('/api/v1/admin/stats');
        const data = await res.json();
        if (data.success) {
          document.getElementById('statUsers').innerText = data.stats.totalUsers;
          document.getElementById('statUnusedKeys').innerText = data.stats.unusedLicenses;
          document.getElementById('statUsedKeys').innerText = data.stats.usedLicenses;
          document.getElementById('statLogs').innerText = data.stats.totalLogs;
        }

        const uRes = await fetch('/api/v1/admin/users');
        const uData = await uRes.json();
        if (uData.success) {
          const tbody = document.querySelector('#recentUsersTable tbody');
          tbody.innerHTML = '';
          uData.users.slice(0, 5).forEach(u => {
            const hwidBadge = u.hwid 
              ? `<span class="tag tag-active">Locked</span>` 
              : `<span class="tag tag-unused">Not Bound</span>`;
            tbody.innerHTML += `
              <tr>
                <td><b>${u.username}</b></td>
                <td><span class="tag tag-unused">${u.level}</span></td>
                <td>${u.expires_at}</td>
                <td>${hwidBadge}</td>
                <td>${u.last_login || 'Never'}</td>
                <td><button class="btn btn-secondary btn-sm" onclick="resetHwid(${u.id})">Reset HWID</button></td>
              </tr>
            `;
          });
        }
      } catch (e) {
        console.error(e);
      }
    }

    async function loadUsers() {
      const res = await fetch('/api/v1/admin/users');
      const data = await res.json();
      const tbody = document.querySelector('#usersTable tbody');
      tbody.innerHTML = '';
      if (data.success) {
        data.users.forEach(u => {
          const isBanned = u.status === 'banned';
          const statusTag = isBanned ? '<span class="tag tag-banned">Banned</span>' : '<span class="tag tag-active">Active</span>';
          tbody.innerHTML += `
            <tr>
              <td>${u.id}</td>
              <td><b>${u.username}</b></td>
              <td><span class="tag tag-unused">${u.level}</span></td>
              <td>${u.expires_at}</td>
              <td class="code-text">${u.hwid ? u.hwid.substring(0, 16) + '...' : '<i style="color:var(--text-dim)">None</i>'}</td>
              <td>${statusTag}</td>
              <td>${u.last_ip || '127.0.0.1'}</td>
              <td style="display:flex; gap:6px;">
                <button class="btn btn-secondary btn-sm" onclick="resetHwid(${u.id})" title="Clear HWID binding">Reset HWID</button>
                <button class="btn btn-sm ${isBanned ? 'btn-primary' : 'btn-danger'}" onclick="toggleBan(${u.id})">${isBanned ? 'Unban' : 'Ban'}</button>
                <button class="btn btn-danger btn-sm" onclick="deleteUser(${u.id})">&times;</button>
              </td>
            </tr>
          `;
        });
      }
    }

    async function loadLicenses() {
      const res = await fetch('/api/v1/admin/licenses');
      const data = await res.json();
      const tbody = document.querySelector('#licensesTable tbody');
      tbody.innerHTML = '';
      if (data.success) {
        data.licenses.forEach(l => {
          const statusTag = l.status === 'unused' 
            ? '<span class="tag tag-active">Unused</span>' 
            : '<span class="tag tag-used">Used</span>';
          tbody.innerHTML += `
            <tr>
              <td><code class="code-text" style="font-weight:600; cursor:pointer;" onclick="copyKey('${l.license_key}')">${l.license_key}</code></td>
              <td>${l.duration_days === 0 ? 'Lifetime' : l.duration_days + ' Days'}</td>
              <td><span class="tag tag-unused">${l.level}</span></td>
              <td>${statusTag}</td>
              <td>${l.used_by || '-'}</td>
              <td>${l.created_at}</td>
              <td>
                <button class="btn btn-secondary btn-sm" onclick="copyKey('${l.license_key}')">Copy</button>
                <button class="btn btn-danger btn-sm" onclick="deleteLicense(${l.id})">&times;</button>
              </td>
            </tr>
          `;
        });
      }
    }

    async function loadApps() {
      const res = await fetch('/api/v1/admin/apps');
      const data = await res.json();
      if (data.success && data.apps.length > 0) {
        const app = data.apps[0];
        currentAppId = app.id;
        document.getElementById('cfgAppName').value = app.name;
        document.getElementById('cfgOwnerId').value = app.owner_id;
        document.getElementById('cfgSecret').value = app.secret;
        document.getElementById('cfgVersion').value = app.version;
        document.getElementById('cfgAnnouncement').value = app.announcement || '';
        document.getElementById('cfgDownloadUrl').value = app.download_url || '';
      }
    }

    async function saveAppConfig() {
      const payload = {
        id: currentAppId,
        secret: document.getElementById('cfgSecret').value,
        version: document.getElementById('cfgVersion').value,
        announcement: document.getElementById('cfgAnnouncement').value,
        download_url: document.getElementById('cfgDownloadUrl').value
      };
      const res = await fetch('/api/v1/admin/apps/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      alert(data.message);
    }

    async function loadVars() {
      const res = await fetch('/api/v1/admin/vars');
      const data = await res.json();
      const tbody = document.querySelector('#varsTable tbody');
      tbody.innerHTML = '';
      if (data.success) {
        data.variables.forEach(v => {
          tbody.innerHTML += `
            <tr>
              <td><code>${v.var_name}</code></td>
              <td><b>${v.var_value}</b></td>
              <td>${v.created_at}</td>
              <td>
                <button class="btn btn-danger btn-sm" onclick="deleteVar(${v.id})">Delete</button>
              </td>
            </tr>
          `;
        });
      }
    }

    async function loadLogs() {
      const res = await fetch('/api/v1/admin/logs');
      const data = await res.json();
      const tbody = document.querySelector('#logsTable tbody');
      tbody.innerHTML = '';
      if (data.success) {
        data.logs.forEach(lg => {
          const isSuccess = lg.status === 'SUCCESS';
          const statBadge = isSuccess 
            ? '<span class="tag tag-active">SUCCESS</span>' 
            : '<span class="tag tag-banned">' + lg.status + '</span>';
          tbody.innerHTML += `
            <tr>
              <td><small>${lg.created_at}</small></td>
              <td><b>${lg.action}</b></td>
              <td>${lg.username || '-'}</td>
              <td>${statBadge}</td>
              <td>${lg.ip_address}</td>
              <td>${lg.details || '-'}</td>
            </tr>
          `;
        });
      }
    }

    async function submitAddUser() {
      const username = document.getElementById('newUsername').value.trim();
      const password = document.getElementById('newPassword').value;
      const level = document.getElementById('newLevel').value;
      const duration_days = document.getElementById('newDuration').value;

      if (!username) { alert('Username required'); return; }

      const res = await fetch('/api/v1/admin/users/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ app_id: currentAppId, username, password, level, duration_days })
      });
      const data = await res.json();
      alert(data.message);
      if (data.success) {
        closeModal('modalAddUser');
        loadUsers();
      }
    }

    async function submitGenerate() {
      const prefix = document.getElementById('genPrefix').value;
      const count = document.getElementById('genCount').value;
      const duration_days = document.getElementById('genDuration').value;
      const level = document.getElementById('genLevel').value;

      const res = await fetch('/api/v1/admin/licenses/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ app_id: currentAppId, prefix, count, duration_days, level })
      });
      const data = await res.json();
      if (data.success) {
        alert(data.message + '\\n\\nFirst key: ' + data.keys[0]);
        closeModal('modalGenerate');
        loadLicenses();
      }
    }

    async function submitAddVar() {
      const var_name = document.getElementById('newVarName').value.trim();
      const var_value = document.getElementById('newVarValue').value.trim();

      const res = await fetch('/api/v1/admin/vars/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ app_id: currentAppId, var_name, var_value })
      });
      const data = await res.json();
      alert(data.message);
      if (data.success) {
        closeModal('modalAddVar');
        loadVars();
      }
    }

    async function resetHwid(userId) {
      if (!confirm('Are you sure you want to reset HWID for this user?')) return;
      const res = await fetch('/api/v1/admin/users/reset-hwid', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId })
      });
      const data = await res.json();
      alert(data.message);
      loadUsers();
    }

    async function toggleBan(userId) {
      const res = await fetch('/api/v1/admin/users/toggle-ban', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId })
      });
      const data = await res.json();
      loadUsers();
    }

    async function deleteUser(userId) {
      if (!confirm('Permanently delete this user?')) return;
      const res = await fetch('/api/v1/admin/users/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId })
      });
      loadUsers();
    }

    async function deleteLicense(licenseId) {
      if (!confirm('Delete this license key?')) return;
      await fetch('/api/v1/admin/licenses/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ license_id: licenseId })
      });
      loadLicenses();
    }

    async function deleteVar(varId) {
      if (!confirm('Delete this variable?')) return;
      await fetch('/api/v1/admin/vars/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ var_id: varId })
      });
      loadVars();
    }

    function copyKey(key) {
      navigator.clipboard.writeText(key).then(() => {
        alert('Copied key to clipboard: ' + key);
      });
    }

    // Startup
    document.addEventListener('DOMContentLoaded', () => {
      document.getElementById('portDisplay').innerText = window.location.port || '80/443';
      loadDashboard();
    });
  </script>
</body>
</html>
"""

def main():
    print("==================================================")
    print("   KRISHU KEYAUTH WEB API SERVER (Complete v1)")
    print("==================================================")
    print(f"[*] Initializing Database at: {DB_FILE}")
    init_db()

    server_address = (HOST, PORT)
    httpd = ThreadingHTTPServer(server_address, KeyAuthHandler)
    httpd.daemon_threads = True
    print(f"[+] Server successfully listening on http://localhost:{PORT}")
    print(f"[+] API URL for Krishu Client: http://localhost:{PORT}/api/v1")
    print(f"[+] Web Admin Dashboard: http://localhost:{PORT}/")
    print(f"[*] Default Login for Form1: User='garaa', Pass='123456'")
    print("==================================================")
    print("[*] Press Ctrl+C to stop the server.")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server stopping...")
        httpd.server_close()
        print("[+] Server stopped.")

if __name__ == "__main__":
    main()
