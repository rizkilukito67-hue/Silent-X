# Krishu KeyAuth API Server (v1)

Server backend pengganti lengkap untuk `https://krishu-keyauth-web.onrender.com/api/v1` yang kompatibel 100% dengan SDK C# `krishuxcheats.cs` dan `Form1.cs`.

---

## ⚡ Fitur Utama

1. **Zero External Dependencies**:
   - Dibuat dengan Python 3 Standard Library (`http.server`, `sqlite3`, `hashlib`, `threading`).
   - Tidak perlu `pip install` apa pun! Cukup klik `run_server.bat` atau `python server.py`.

2. **Endpoint Lengkap Sesuai Krishu C# SDK**:
   - `POST /api/v1/init` — Inisialisasi aplikasi, validasi nama app & secret, pesan announcement & download update.
   - `POST /api/v1/login` — Autentikasi user, pengecekan expiry/lifetime, auto-bind HWID & proteksi multi-PC.
   - `POST /api/v1/register` — Registrasi akun baru menggunakan License Key.
   - `POST /api/v1/license` — Login langsung menggunakan License Key (Key-only mode).
   - `GET /api/v1/var/<varName>` — Mengambil variabel dinamis cheat (seperti status undetected, fov, version).
   - `POST /api/v1/check` — Session check / heartbeat.
   - `POST /api/v1/hwid-reset` — Reset HWID agar akun bisa dipakai di PC baru.

3. **Web Admin Dashboard Modern**:
   - URL: `http://localhost:5000/` atau root domain.
   - Tema gelap noir/cyberpunk dengan aksen Crimson Red.
   - Manajemen User (Tambah, Reset HWID, Ban/Unban, Ganti Durasi Expiry, Hapus).
   - Generator License Key otomatis (1 Hari, 7 Hari, 30 Hari, Lifetime).
   - Pengaturan App (Ganti secret, version, link download, pesan pengumuman).
   - Live Audit Logs (Catatan IP, HWID, dan waktu login setiap user).

---

## 🚀 Cara Menjalankan di Localhost (Komputer Anda)

1. Buka folder `KrishuKeyAuthServer`.
2. Klik dua kali file **`run_server.bat`** (atau jalankan terminal: `python server.py`).
3. Server otomatis aktif di:
   - **API URL**: `http://localhost:5000/api/v1`
   - **Dashboard**: `http://localhost:5000/`
4. Buka file C# [Form1.cs](file:///c:/Users/rizki/Downloads/Internal%20Hide/Internal/SLXPanel/Form1.cs#L87-L94) baris 92, ubah `apiUrl` menjadi:
   ```csharp
   public static KrishuXCheats.api KeyAuthApp = new KrishuXCheats.api(
       name: "garaa-App-1",
       ownerid: "garaa",
       secret: "1fb641dc27d1400cd42c88aeae239c74",
       version: "1.0.0",
       apiUrl: "http://localhost:5000/api/v1"
   );
   ```
5. Jalankan aplikasi cheat Anda! Anda bisa langsung login dengan akun bawaan:
   - **Username**: `garaa`
   - **Password**: `123456`
   - **Durasi**: Lifetime

---

## 🌐 Cara Deploy Gratis ke Render.com (Agar Online 24/7)

Agar panel cheat bisa diakses orang lain dari internet tanpa harus menyalakan PC Anda:

1. Buat repository baru di **GitHub** (misalnya `krishu-keyauth-api`).
2. Upload semua file di folder `KrishuKeyAuthServer` ke repository GitHub tersebut.
3. Buka [https://render.com](https://render.com) dan login dengan akun GitHub Anda.
4. Klik **New +** > **Web Service**.
5. Pilih repository GitHub Anda tadi.
6. Konfigurasi otomatis:
   - **Name**: `krishu-keyauth-web` (atau nama pilihan Anda)
   - **Runtime**: `Python 3`
   - **Build Command**: *(kosongkan)*
   - **Start Command**: `python server.py`
   - **Instance Type**: `Free`
7. Klik **Create Web Service**.
8. Setelah statusnya **Live**, Render akan memberikan link HTTPS publik, contoh:
   `https://krishu-keyauth-api-xxxx.onrender.com`
9. Di [Form1.cs](file:///c:/Users/rizki/Downloads/Internal%20Hide/Internal/SLXPanel/Form1.cs#L92), masukkan URL tersebut ditambah `/api/v1`:
   ```csharp
   apiUrl: "https://krishu-keyauth-api-xxxx.onrender.com/api/v1"
   ```

---

## 🔑 Data Akun Bawaan

| Role | Username | Password | Tipe Akses |
|---|---|---|---|
| User Cheat | `garaa` | `123456` | Lifetime VIP |
| Admin | `admin` | `admin123` | Lifetime Admin |
| App Secret | `1fb641dc27d1400cd42c88aeae239c74` | - | - |
| App Name | `garaa-App-1` | - | - |
| Owner ID | `garaa` | - | - |

License Keys siap pakai bawaan:
- `KXC-LIFE-AAAA-BBBB-CCCC` (Lifetime)
- `KXC-30D-1111-2222-3333` (30 Hari)
- `KXC-7D-4444-5555-6666` (7 Hari)
- `KXC-1D-7777-8888-9999` (1 Hari)

---

## 🧪 Testing API Otomatis

Untuk memastikan seluruh API berjalan 100%:
```bash
python test_client.py
```
Hasil test akan memvalidasi `/init`, `/login`, `/license`, `/var`, dan proteksi password secara instan.
