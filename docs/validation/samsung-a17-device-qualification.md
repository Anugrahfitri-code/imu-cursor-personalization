# Qualification Perangkat Samsung Galaxy A17 4G

**Perangkat:** Samsung Galaxy A17 4G (`SM-A175F`)
**Tanggal qualification:** 7 September 2026
**Status:** M0 PASS | M1 PASS | M2 pending

## 1. Tujuan

Dokumen ini mencatat qualification awal Samsung Galaxy A17 4G sebagai kandidat perangkat final pada penelitian pengendalian kursor berbasis gerakan smartphone menggunakan data Inertial Measurement Unit (IMU).

Qualification dilakukan sebelum studi pengguna untuk memastikan bahwa perangkat:

- memiliki accelerometer dan gyroscope yang dapat diakses melalui Android Sensor API;
- dapat direkam oleh aplikasi penelitian;
- menghasilkan timestamp sensor yang monotonic;
- memiliki sampling yang stabil pada beberapa run independen; dan
- tidak menunjukkan missing atau duplicate sequence pada acquisition lokal.

Hasil dalam dokumen ini hanya mencakup M0 dan M1. Perangkat belum dinyatakan sebagai final qualified research device sampai pengujian transport UDP, reliability, dan clock synchronization selesai.

---

## 2. Identitas Perangkat

Identitas diperoleh menggunakan ADB langsung dari perangkat.

```text
Manufacturer : samsung
Model        : SM-A175F
Device       : a17
Product      : a17xx
Android      : 16
API Level    : 36
```

Build fingerprint saat qualification:

```text
samsung/a17xx/a17:16/BP4A.251205.006/A175FXXS6CZG1_OXM6CZG1:user/release-keys
```

Seluruh run yang dibahas dalam dokumen ini dilakukan menggunakan unit perangkat yang sama.

---

## 3. Sensor IMU

Pemeriksaan `dumpsys sensorservice` menunjukkan dua sensor utama yang digunakan penelitian:

### Accelerometer

```text
Name         : LSM6DSVTR Accelerometer
Vendor       : STM
Android type : android.sensor.accelerometer
Reporting    : continuous
```

`sensorservice` melaporkan:

```text
minRate : 6.25 Hz
maxRate : 500.00 Hz
```

Metadata yang diperoleh melalui aplikasi penelitian:

```text
Resolution    : 0.0023942017 m/s²
Maximum range : 78.4532 m/s²
Min delay     : 8000 µs
```

### Gyroscope

```text
Name         : LSM6DSVTR Gyroscope
Vendor       : STM
Android type : android.sensor.gyroscope
Reporting    : continuous
```

`sensorservice` melaporkan:

```text
minRate : 6.25 Hz
maxRate : 500.00 Hz
```

Metadata yang diperoleh melalui aplikasi penelitian:

```text
Resolution    : 6.1086525E-4 rad/s
Maximum range : 17.453032 rad/s
Min delay     : 8000 µs
```

Versi uncalibrated dari accelerometer dan gyroscope juga tersedia pada perangkat. Namun, acquisition utama penelitian menggunakan tipe Android standar:

```text
TYPE_ACCELEROMETER
TYPE_GYROSCOPE
```

Sensor proprietary Samsung seperti Interrupt Gyroscope, VDIS Gyroscope, dan AOIS Sensor tidak digunakan sebagai sumber data penelitian.

Perlu dicatat bahwa `sensorservice` melaporkan kemampuan rate yang lebih tinggi daripada `minDelay` yang terlihat melalui aplikasi. Karena itu, keputusan sampling penelitian tidak didasarkan hanya pada deklarasi sensor, tetapi terutama pada timestamp aktual yang dihasilkan oleh aplikasi penelitian.

---

## 4. M0 — Device and Sensor Qualification

M0 digunakan untuk memastikan bahwa kandidat perangkat menyediakan IMU yang sesuai dan dapat diakses melalui aplikasi penelitian.

Probe yang digunakan:

```text
m0_a17_sensor_probe_01
```

Aplikasi penelitian berhasil:

- mendeteksi Samsung `SM-A175F`;
- mengakses accelerometer `LSM6DSVTR`;
- mengakses gyroscope `LSM6DSVTR`;
- menerima `SensorEvent.timestamp`;
- merekam data kedua sensor;
- menyimpan metadata sensor; dan
- menghasilkan sequence number untuk audit acquisition.

Konfigurasi sampling yang diminta aplikasi:

```text
requested_sampling_us = 10000
requested_sampling_hz = 100.0
```

Pada probe awal, observed sampling berada di sekitar 125 Hz.

### Hasil M0

```text
Device identity             PASS
Accelerometer availability  PASS
Gyroscope availability      PASS
Android Sensor API access   PASS
Research application access PASS
Raw sensor recording        PASS
```

**Status M0-A17: PASS**

---

## 5. M1 — Sampling and Timestamp Qualification

M1 dilakukan menggunakan tiga stationary run independen:

```text
m1_a17_stationary_01
m1_a17_stationary_02
m1_a17_stationary_03
```

Smartphone ditempatkan datar di atas meja dengan layar menghadap ke atas.

Gerakan saat memulai atau menghentikan recording tidak digunakan sebagai dasar penilaian stationary behavior. Fokus M1 adalah integritas acquisition dan karakteristik temporal sensor.

Konfigurasi aplikasi tidak diubah antar-run:

```text
requested_sampling_us = 10000
requested_sampling_hz = 100.0
```

Timestamp sensor utama:

```text
SensorEvent.timestamp
```

Timestamp callback:

```text
SystemClock.elapsedRealtimeNanos()
```

Sequence audit:

```text
seq_global
seq_sensor
```

---

## 6. Hasil Sampling

### Ringkasan

| Metrik | Run 01 | Run 02 | Run 03 |
|---|---:|---:|---:|
| ACC samples | 11,508 | 8,408 | 7,916 |
| GYRO samples | 11,508 | 8,408 | 7,916 |
| ACC duration | 92.056 s | 67.256 s | 63.320 s |
| GYRO duration | 92.056 s | 67.256 s | 63.320 s |
| ACC observed rate | 124.9999 Hz | 124.9991 Hz | 124.9999 Hz |
| GYRO observed rate | 124.9999 Hz | 125.0000 Hz | 124.9999 Hz |
| ACC median Δt | 7.9957 ms | 7.9957 ms | 7.9957 ms |
| GYRO median Δt | 7.9957 ms | 7.9957 ms | 7.9957 ms |
| ACC P95 Δt | 8.0264 ms | 8.0265 ms | 8.0264 ms |
| GYRO P95 Δt | 8.0264 ms | 8.0264 ms | 8.0264 ms |

Observed rate dihitung dari jumlah interval dan rentang `SensorEvent.timestamp`, bukan dari durasi yang diharapkan pengguna.

Hasil ketiga run menunjukkan bahwa request 100 Hz tidak menghasilkan raw event tepat 100 Hz. Pada konfigurasi aplikasi saat qualification, kedua sensor secara konsisten menghasilkan event sekitar 125 Hz dengan interval sekitar 8 ms.

Raw timestamp tidak dimodifikasi untuk membuat acquisition terlihat 100 Hz.

---

## 7. Sequence dan Timestamp Integrity

Hasil pemeriksaan integritas:

| Pemeriksaan | Run 01 | Run 02 | Run 03 |
|---|---:|---:|---:|
| Missing global sequence | 0 | 0 | 0 |
| Duplicate global sequence | 0 | 0 | 0 |
| Missing ACC sequence | 0 | 0 | 0 |
| Missing GYRO sequence | 0 | 0 | 0 |
| Duplicate ACC timestamp | 0 | 0 | 0 |
| Duplicate GYRO timestamp | 0 | 0 | 0 |
| Non-monotonic ACC timestamp | 0 | 0 | 0 |
| Non-monotonic GYRO timestamp | 0 | 0 | 0 |

Android sensor accuracy pada seluruh sampel dari ketiga run adalah:

```text
3
```

Tidak ditemukan discontinuity pada sequence acquisition lokal selama ketiga run M1.

---

## 8. Callback Timing

Callback delay didefinisikan sebagai:

```text
callback_elapsed_ns - sensor_ts_phone_ns
```

Hasil:

| Metrik | Run 01 | Run 02 | Run 03 |
|---|---:|---:|---:|
| ACC P50 | 3.000 ms | 2.520 ms | 2.850 ms |
| ACC P95 | 3.593 ms | 3.076 ms | 3.539 ms |
| ACC maximum | 8.160 ms | 7.430 ms | 7.379 ms |
| GYRO P50 | 3.530 ms | 2.494 ms | 3.536 ms |
| GYRO P95 | 4.188 ms | 3.076 ms | 4.119 ms |
| GYRO maximum | 8.628 ms | 8.907 ms | 8.072 ms |

Nilai ini digunakan sebagai engineering characterization pada sisi smartphone.

Callback delay bukan sensor-to-photon latency dan tidak digunakan untuk membuat klaim mengenai display latency.

---

## 9. Hubungan Temporal Accelerometer dan Gyroscope

Accelerometer dan gyroscope tidak diasumsikan simultaneous hanya karena memiliki `seq_sensor` dengan ordinal yang sama.

Pada Run 01 dan Run 03, pasangan ACC dan GYRO dengan ordinal sequence yang sama memiliki timestamp identik pada data yang direkam.

Pada Run 02 terdapat phase offset yang konsisten.

Median:

```text
GYRO timestamp - ACC timestamp
≈ +3.998 ms
```

Rentang utama offset berada sangat dekat dengan 4 ms.

Temuan ini menunjukkan bahwa:

```text
ACC seq_sensor = n
```

tidak boleh secara otomatis dianggap synchronous dengan:

```text
GYRO seq_sensor = n
```

Oleh karena itu, alignment antar-sensor pada pipeline penelitian akan menggunakan timestamp, bukan equality sequence number.

Prinsip yang digunakan:

```text
raw ACC timestamp
        │
        ├── timestamp-based alignment
        │
raw GYRO timestamp
        │
        ▼
common time representation
```

Definisi common time grid dan metode resampling belum dibekukan pada M1.

---

## 10. Keputusan Engineering setelah M1

Berdasarkan tiga run independen pada Samsung Galaxy A17 4G:

```text
Observed raw acquisition ≈ 125 Hz
```

dengan karakteristik berikut:

- rate ACC dan GYRO konsisten antar-run;
- median sampling interval sekitar 7.996 ms;
- tidak ditemukan missing sequence;
- tidak ditemukan duplicate sequence;
- tidak ditemukan duplicate sensor timestamp;
- tidak ditemukan non-monotonic sensor timestamp; dan
- callback timing tetap berada pada skala beberapa milidetik.

Konfigurasi:

```text
requested_sampling_us = 10000
```

tetap dipertahankan pada tahap qualification berikutnya agar M2 dilakukan menggunakan acquisition configuration yang sama dengan M1.

M1 tidak digunakan untuk mengubah raw timestamp atau memaksa event menjadi tepat 100 Hz.

**Status M1-A17: PASS**

---

## 11. Keputusan yang Belum Dibekukan

M1 hanya mengkarakterisasi acquisition mentah.

Keputusan berikut belum dibekukan:

```text
analysis sampling rate
common time grid
resampling method
interpolation method
temporal model window length
preprocessing filter parameters
```

Keputusan tersebut akan ditetapkan pada tahap desain preprocessing dan experimental pipeline.

Perbandingan P0, P2C, L0, dan L2C harus menggunakan definisi preprocessing yang konsisten, kecuali terdapat alasan metodologis yang ditentukan sebelum evaluasi final.

---

## 12. Data yang Digunakan

Raw engineering data disimpan lokal di:

```text
bench_data/a17/
```

dan tidak dimasukkan ke Git repository.

### M0

```text
imu_m0_a17_sensor_probe_01_20260907_200642_572.csv
meta_m0_a17_sensor_probe_01_20260907_200642_572.txt
a17_sensorservice_m0_20260907.txt
```

### M1

```text
imu_m1_a17_stationary_01_20260907_203645_274.csv
meta_m1_a17_stationary_01_20260907_203645_274.txt

imu_m1_a17_stationary_02_20260907_204347_473.csv
meta_m1_a17_stationary_02_20260907_204347_473.txt

imu_m1_a17_stationary_03_20260907_212832_731.csv
meta_m1_a17_stationary_03_20260907_212832_731.txt
```

Raw data dipisahkan dari source repository agar repository tetap ringan dan agar runtime engineering data tidak bercampur dengan source code.

Dokumen ini menyimpan ringkasan hasil yang diperlukan untuk audit keputusan engineering.

---

## 13. Batas Klaim

M0 dan M1 mendukung qualification pada tingkat device, sensor, sampling, dan timestamp acquisition.

Hasil ini belum membuktikan:

- reliability transport UDP untuk durasi panjang;
- packet-loss behavior pada A17;
- clock synchronization quality;
- end-to-end latency;
- sensor-to-photon latency;
- kesiapan sistem untuk studi peserta;
- peningkatan performa pointing;
- efektivitas personalisasi; atau
- keunggulan learned system dibanding sistem parametrik.

Metrik tersebut harus diuji pada milestone yang sesuai.

---

## 14. Status Qualification

Status saat ini:

```text
M0-A17  Device and sensor qualification      PASS
M1-A17  Sampling and timestamp qualification PASS

M2.1-A17  UDP smoke test                     PENDING
M2.2-A17  Transport reliability              PENDING
M2.3-A17  Clock synchronization              PENDING
```

Samsung Galaxy A17 4G masih berstatus:

```text
candidate final research device
```

Perangkat belum disebut sebagai final qualified research device.

---

## 15. Tahap Berikutnya

Qualification dilanjutkan dengan urutan:

```text
M2.1-A17
UDP smoke test
        │
        ▼
M2.2-A17
transport reliability
        │
        ▼
M2.3-A17
clock synchronization
        │
        ├── 2-minute bench
        ├── 10-minute bench
        └── 25-minute bench
        │
        ▼
final device-dependent engineering review
        │
        ▼
final research device freeze
```

Tidak ada data peserta manusia yang dikumpulkan pada M0 atau M1.
