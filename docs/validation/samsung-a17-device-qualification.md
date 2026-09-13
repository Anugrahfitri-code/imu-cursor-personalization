# Qualification Perangkat Samsung Galaxy A17 4G

**Perangkat:** Samsung Galaxy A17 4G (`SM-A175F`)<br>
**Tanggal qualification:** 7 September 2026<br>
**Status:** M0 PASS | M1 PASS | M2.1 PASS | M2.2-M2.3 pending

## 1. Tujuan

Dokumen ini mencatat proses qualification Samsung Galaxy A17 4G sebagai kandidat perangkat final pada penelitian pengendalian kursor berbasis gerakan smartphone menggunakan data Inertial Measurement Unit (IMU).

Qualification dilakukan sebelum studi pengguna untuk memastikan bahwa perangkat:

- memiliki accelerometer dan gyroscope yang dapat diakses melalui Android Sensor API;
- dapat direkam oleh aplikasi penelitian;
- menghasilkan timestamp sensor yang monotonic;
- memiliki sampling yang stabil pada beberapa run independen;
- tidak menunjukkan missing atau duplicate sequence pada acquisition lokal; dan
- dapat melakukan streaming data IMU melalui UDP ke PC penelitian.

Qualification dilakukan secara bertahap.

Pada dokumen ini telah diselesaikan:

```text
M0    Device and sensor qualification
M1    Sampling and timestamp qualification
M2.1  UDP smoke test
```

Samsung Galaxy A17 4G belum dinyatakan sebagai final qualified research device sampai pengujian reliability M2.2 dan clock synchronization M2.3 selesai.

---

## 2. Identitas Perangkat

Identitas perangkat diperoleh menggunakan ADB secara langsung.

```text
Manufacturer : samsung
Model        : SM-A175F
Device       : a17
Product      : a17xx
Android      : 16
API Level    : 36
```

Build fingerprint pada saat qualification:

```text
samsung/a17xx/a17:16/BP4A.251205.006/A175FXXS6CZG1_OXM6CZG1:user/release-keys
```

Seluruh run yang dibahas dalam dokumen ini dilakukan menggunakan unit perangkat yang sama.

---

## 3. Sensor IMU

Pemeriksaan Android `dumpsys sensorservice` menunjukkan bahwa perangkat menyediakan accelerometer dan gyroscope melalui tipe sensor Android standar.

### Accelerometer

```text
Name         : LSM6DSVTR Accelerometer
Vendor       : STM
Android type : android.sensor.accelerometer
Reporting    : continuous
```

`sensorservice` melaporkan:

```text
Min rate : 6.25 Hz
Max rate : 500.00 Hz
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
Min rate : 6.25 Hz
Max rate : 500.00 Hz
```

Metadata yang diperoleh melalui aplikasi penelitian:

```text
Resolution    : 6.1086525E-4 rad/s
Maximum range : 17.453032 rad/s
Min delay     : 8000 µs
```

Versi uncalibrated dari accelerometer dan gyroscope juga tersedia pada perangkat.

Acquisition utama penelitian tetap menggunakan tipe sensor Android standar:

```text
TYPE_ACCELEROMETER
TYPE_GYROSCOPE
```

Sensor proprietary Samsung seperti:

```text
Interrupt Gyroscope
VDIS Gyroscope
AOIS Sensor
```

tidak digunakan sebagai sumber data penelitian.

Perlu dicatat bahwa `sensorservice` melaporkan kemampuan rate yang lebih tinggi daripada nilai `minDelay` yang terlihat melalui aplikasi.

Karena itu, keputusan sampling penelitian tidak didasarkan hanya pada deklarasi sensor, tetapi terutama pada timestamp aktual yang dihasilkan selama acquisition.

---

## 4. M0 - Device and Sensor Qualification

M0 digunakan untuk memastikan bahwa kandidat perangkat menyediakan IMU yang sesuai dan dapat digunakan oleh aplikasi penelitian.

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
- menyimpan metadata sensor;
- menghasilkan sequence number untuk audit acquisition; dan
- menyimpan raw recording ke external application storage.

Konfigurasi sampling yang diminta aplikasi:

```text
requested_sampling_us = 10000
requested_sampling_hz = 100.0
```

Pada probe awal, observed sampling berada di sekitar:

```text
125 Hz
```

Tidak ditemukan indikasi bahwa gyroscope utama merupakan virtual atau pseudo gyroscope.

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

## 5. M1 - Sampling and Timestamp Qualification

M1 dilakukan untuk menguji konsistensi acquisition pada beberapa run independen.

Tiga stationary run digunakan:

```text
m1_a17_stationary_01
m1_a17_stationary_02
m1_a17_stationary_03
```

Smartphone ditempatkan datar di atas meja dengan layar menghadap ke atas.

Gerakan pada saat memulai atau menghentikan recording tidak digunakan sebagai dasar penilaian stationary behavior.

Fokus M1 adalah:

- sampling stability;
- sequence integrity;
- timestamp monotonicity;
- callback timing; dan
- hubungan temporal antara accelerometer dan gyroscope.

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

## 6. Hasil Sampling M1

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

Observed rate dihitung berdasarkan jumlah interval dan rentang `SensorEvent.timestamp`, bukan berdasarkan durasi recording yang diharapkan pengguna.

Ketiga run menunjukkan bahwa request:

```text
100 Hz
```

tidak menghasilkan raw event tepat 100 Hz.

Pada konfigurasi aplikasi saat qualification, kedua sensor secara konsisten menghasilkan event sekitar:

```text
125 Hz
```

dengan interval sekitar:

```text
8 ms
```

Raw timestamp tidak dimodifikasi untuk membuat acquisition terlihat sebagai 100 Hz.

---

## 7. Sequence dan Timestamp Integrity

Hasil pemeriksaan integritas acquisition:

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

Tidak ditemukan discontinuity pada local acquisition sequence selama ketiga run M1.

---

## 8. Callback Timing

Callback delay didefinisikan sebagai:

```text
callback_elapsed_ns - sensor_ts_phone_ns
```

Hasil engineering characterization:

| Metrik | Run 01 | Run 02 | Run 03 |
|---|---:|---:|---:|
| ACC P50 | 3.000 ms | 2.520 ms | 2.850 ms |
| ACC P95 | 3.593 ms | 3.076 ms | 3.539 ms |
| ACC maximum | 8.160 ms | 7.430 ms | 7.379 ms |
| GYRO P50 | 3.530 ms | 2.494 ms | 3.536 ms |
| GYRO P95 | 4.188 ms | 3.076 ms | 4.119 ms |
| GYRO maximum | 8.628 ms | 8.907 ms | 8.072 ms |

Nilai tersebut digunakan sebagai engineering characterization pada sisi smartphone.

Callback delay bukan sensor-to-photon latency dan tidak digunakan untuk membuat klaim mengenai display latency.

---

## 9. Hubungan Temporal Accelerometer dan Gyroscope

Accelerometer dan gyroscope tidak diasumsikan simultaneous hanya karena memiliki `seq_sensor` dengan ordinal yang sama.

Pada:

```text
Run 01
Run 03
```

pasangan ACC dan GYRO dengan ordinal sequence yang sama memiliki timestamp identik pada data yang direkam.

Pada:

```text
Run 02
```

terdapat phase offset yang konsisten.

Median:

```text
GYRO timestamp - ACC timestamp
≈ +3.998 ms
```

Temuan tersebut menunjukkan bahwa:

```text
ACC seq_sensor = n
```

tidak boleh secara otomatis dianggap synchronous dengan:

```text
GYRO seq_sensor = n
```

Karena itu, alignment antar-sensor pada pipeline penelitian menggunakan timestamp sebagai dasar temporal, bukan equality sequence number.

Prinsip:

```text
raw ACC timestamp
        |
        +---- timestamp-based alignment
        |
raw GYRO timestamp
        |
        v
common time representation
```

Definisi common time grid dan metode resampling belum dibekukan pada M1.

---

## 10. Keputusan Engineering setelah M1

Berdasarkan tiga run independen pada Samsung Galaxy A17 4G:

```text
Observed raw acquisition ≈ 125 Hz
```

dengan karakteristik:

- rate ACC dan GYRO konsisten antar-run;
- median sampling interval sekitar 7.996 ms;
- tidak ditemukan missing sequence;
- tidak ditemukan duplicate sequence;
- tidak ditemukan duplicate sensor timestamp;
- tidak ditemukan non-monotonic sensor timestamp; dan
- callback timing berada pada skala beberapa milidetik.

Konfigurasi:

```text
requested_sampling_us = 10000
```

dipertahankan pada tahap qualification selanjutnya agar M2 menggunakan acquisition configuration yang sama dengan M1.

M1 tidak digunakan untuk mengubah raw timestamp atau memaksa raw event menjadi tepat 100 Hz.

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

## 12. Data M0 dan M1

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

Raw data dipisahkan dari source repository agar repository tetap ringan dan runtime engineering data tidak bercampur dengan source code.

Dokumen ini menyimpan ringkasan hasil yang diperlukan untuk audit keputusan engineering.

---

## 13. M2.1 - UDP Smoke Test

M2.1 digunakan untuk memastikan bahwa data IMU dapat dikirim dari Samsung Galaxy A17 4G ke PC melalui jalur UDP penelitian sebelum masuk ke reliability testing berdurasi lebih panjang.

Konfigurasi transport:

```text
Protocol version : 1
Transport        : UDP
Destination port : 5005
PC receiver bind : 0.0.0.0:5005
```

Pada qualification ini, smartphone dan laptop menggunakan jaringan Wi-Fi lokal yang sama.

Konfigurasi jaringan pada valid run:

```text
Samsung A17 Wi-Fi : 10.109.123.52/24
Laptop Wi-Fi      : 10.109.123.69/24
Network           : 10.109.123.0/24
UDP target        : 10.109.123.69:5005
```

Receiver PC:

```text
pc/receiver/udp_receiver.py
```

Receiver melakukan accounting terhadap:

- valid packet;
- invalid packet;
- unique sequence;
- missing packet;
- duplicate packet;
- out-of-order packet; dan
- longest missing burst.

---

## 14. Technical-Invalid Run M2.1

Run pertama:

```text
m2_1_a17_udp_01
```

tidak digunakan sebagai qualification evidence.

Pada run tersebut, USB tethering pada smartphone diketahui masih aktif secara tidak sengaja.

Kondisi tersebut menambahkan jalur jaringan lain di samping Wi-Fi dan tidak sesuai dengan network configuration yang dimaksudkan untuk qualification.

Metadata Android mencatat:

```text
udp_target_ip=10.109.123.69
udp_target_port=5005

final_total_samples=8100
final_acc_samples=4050
final_gyro_samples=4050

final_udp_packets_sent=6018
final_network_queue_drops=0
final_udp_send_errors=0
final_local_queue_remaining=0
final_network_queue_remaining=2081
```

Receiver PC pada run tersebut tidak menerima packet dari stream penelitian.

Untuk memisahkan kemungkinan masalah aplikasi dari jalur jaringan, dilakukan diagnostic datagram menggunakan `toybox nc` dari A17 menuju:

```text
10.109.123.69:5005
```

Receiver PC menerima datagram tersebut dan mengklasifikasikannya sebagai invalid packet karena payload diagnostic tidak mengikuti UDP protocol v1 penelitian.

Hasil diagnostic tersebut menunjukkan bahwa A17 dan PC dapat berkomunikasi melalui UDP port 5005.

Setelah diketahui USB tethering aktif, tethering dimatikan dan konfigurasi jaringan diverifikasi ulang sebelum replacement run.

Run pertama diklasifikasikan sebagai:

```text
TECHNICAL_INVALID
```

Alasan:

```text
Unintended USB tethering was active during the run,
introducing an additional network path and violating
the intended Wi-Fi-only qualification condition.
```

Klasifikasi technical invalid tidak digunakan untuk menyatakan bahwa USB tethering secara definitif merupakan satu-satunya penyebab paket penelitian tidak diterima.

Run dikeluarkan dari qualification evidence karena kondisi jaringan tidak sesuai dengan konfigurasi yang telah ditentukan.

Run tetap disimpan dalam engineering archive untuk menjaga audit trail.

---

## 15. Valid M2.1 Replacement Run

Replacement run:

```text
m2_1_a17_udp_smoke_02
```

dijalankan setelah konfigurasi berikut diverifikasi:

```text
USB tethering : OFF
Wi-Fi         : ON

A17           : 10.109.123.52/24
Laptop        : 10.109.123.69/24

UDP target    : 10.109.123.69:5005
```

Metadata Android:

```text
session_id=20260907_232510_633
record_name=m2_1_a17_udp_smoke_02

final_total_samples=10232
final_acc_samples=5116
final_gyro_samples=5116

final_udp_packets_sent=10232
final_network_queue_drops=0
final_udp_send_errors=0
final_local_queue_remaining=0
final_network_queue_remaining=0
```

Receiver PC mencatat:

```text
Total valid packets : 10232
Invalid packets     : 0

received     : 10232
missing      : 0
duplicate    : 0
loss         : 0.000000%
max burst    : 0
out-of-order : 0
```

Perbandingan end-to-end:

```text
Android total samples : 10232
Android UDP sent      : 10232
PC valid received     : 10232
```

Dengan demikian:

```text
10232 / 10232
```

packet yang dilaporkan berhasil dikirim oleh Android juga diterima sebagai valid packet oleh receiver PC pada valid qualification run.

Tidak ditemukan:

```text
missing packet
duplicate packet
out-of-order packet
invalid packet
network queue drop
UDP send error
residual network queue
residual local writer queue
```

pada valid smoke run.

**Status M2.1-A17: PASS**

---

## 16. Keputusan Engineering setelah M2.1

M2.1 mendukung bahwa jalur berikut dapat beroperasi secara end-to-end pada Samsung Galaxy A17 4G dalam konfigurasi qualification yang digunakan:

```text
Accelerometer / Gyroscope
        |
        v
Android SensorEvent
        |
        v
Network queue
        |
        v
UDP protocol v1
        |
        v
Wi-Fi local network
        |
        v
PC UDP receiver :5005
        |
        v
Sequence and reliability accounting
```

Valid smoke run tidak digunakan untuk menyimpulkan long-duration network reliability.

M2.1 hanya menunjukkan bahwa kombinasi:

```text
sensor acquisition
+
Android UDP sender
+
local Wi-Fi path
+
PC receiver
```

dapat beroperasi bersama tanpa packet discrepancy pada short qualification run yang diuji.

Reliability untuk durasi lebih panjang diuji secara terpisah pada M2.2.

---

## 17. Data M2.1

Raw valid-run evidence disimpan lokal di:

```text
bench_data/a17/m2_1/
```

File valid run:

```text
imu_m2_1_a17_udp_smoke_02_20260907_232510_633.csv
meta_m2_1_a17_udp_smoke_02_20260907_232510_633.txt
pc_udp_m2_1_a17_udp_smoke_02.csv
```

Technical-invalid evidence disimpan di:

```text
bench_data/a17/m2_1/technical_invalid/
```

File:

```text
imu_m2_1_a17_udp_01_20260907_224357_398.csv
meta_m2_1_a17_udp_01_20260907_224357_398.txt
technical_invalid.txt
```

Raw engineering data tetap dikecualikan dari Git repository.

Repository hanya menyimpan ringkasan qualification yang diperlukan untuk audit metodologi dan engineering decision.

---

## 18. Batas Klaim

Hasil M0, M1, dan M2.1 mendukung qualification pada tingkat:

```text
device identity
sensor availability
raw acquisition
sampling characterization
timestamp integrity
short-run UDP transport
```

Hasil tersebut belum membuktikan:

- reliability UDP untuk durasi panjang;
- packet-loss behavior pada sustained load;
- long-duration queue stability;
- clock synchronization quality;
- end-to-end latency;
- sensor-to-photon latency;
- kesiapan sistem untuk studi peserta;
- peningkatan performa pointing;
- efektivitas personalisasi; atau
- keunggulan learned system dibanding sistem parametrik.

Metrik tersebut diuji pada milestone yang sesuai.

---

## 19. Status Qualification

Status saat ini:

```text
M0-A17
Device and sensor qualification
PASS

M1-A17
Sampling and timestamp qualification
PASS

M2.1-A17
UDP smoke test
PASS

M2.2-A17
Transport reliability
PENDING

M2.3-A17
Clock synchronization
PENDING
```

Samsung Galaxy A17 4G masih berstatus:

```text
candidate final research device
```

Perangkat belum disebut sebagai:

```text
final qualified research device
```

karena qualification M2.2 dan M2.3 belum selesai.

---

## 20. Tahap Berikutnya

Qualification dilanjutkan dengan:

```text
M2.2-A17
transport reliability
        |
        +-- short-duration qualification
        +-- medium-duration qualification
        +-- long-duration qualification
        |
        v
M2.3-A17
clock synchronization
        |
        +-- 2-minute bench
        +-- 10-minute bench
        +-- 25-minute bench
        |
        v
final device-dependent engineering review
        |
        v
final research device freeze
```

Durasi dan acceptance criteria M2.2 mengikuti reliability protocol yang telah digunakan pada engineering-development device, kecuali terdapat evidence khusus A17 yang memerlukan perubahan sebelum qualification final.

Tidak ada data peserta manusia yang dikumpulkan pada M0, M1, atau M2.1.