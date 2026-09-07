# Personalisasi Pengendalian Kursor Berbasis IMU Smartphone

Repository penelitian untuk pengembangan dan evaluasi sistem interaksi kursor ruang bebas berbasis gerakan smartphone menggunakan data **Inertial Measurement Unit (IMU)**.

Penelitian ini berfokus pada personalisasi pengendalian kursor bagi pengguna baru serta membandingkan pendekatan **parametrik berdimensi rendah** dengan pendekatan **temporal berbasis deep learning** pada beban kalibrasi pengguna yang sama.

Target penelitian diarahkan pada publikasi jurnal nasional terakreditasi dengan target minimal **SINTA 2**.

---

## Judul Penelitian

**Personalisasi Pengendalian Kursor Berbasis Gerakan Smartphone Menggunakan IMU: Perbandingan Sistem Parametrik dan Temporal Berbasis Pembelajaran pada Pengguna Baru**

---

## Latar Penelitian

Smartphone modern memiliki sensor gerak seperti accelerometer dan gyroscope yang memungkinkan perangkat digunakan sebagai media interaksi ruang bebas.

Namun, karakteristik gerakan pengguna dapat berbeda satu sama lain. Pemetaan gerakan yang sama belum tentu memberikan pengalaman pointing yang sama pada setiap pengguna.

Penelitian ini menguji apakah kalibrasi pengguna yang singkat dapat meningkatkan performa pengendalian kursor dan apakah sistem temporal berbasis deep learning memberikan keuntungan HCI yang cukup besar untuk membenarkan tambahan kompleksitasnya dibanding sistem parametrik yang lebih sederhana.

Fokus penelitian bukan sekadar membuat smartphone berfungsi sebagai mouse, tetapi mengevaluasi:

- personalisasi sistem interaksi;
- efektivitas kalibrasi singkat;
- perbandingan keluarga sistem;
- performa pengguna;
- kompleksitas komputasi;
- adaptation time;
- jumlah parameter yang berubah;
- latency;
- trade-off antara performa dan kompleksitas.

---

# Pertanyaan Penelitian

## RQ1

Sejauh mana kalibrasi parametrik singkat 2C meningkatkan performa penunjukan ruang bebas pada pengguna baru dibanding pemetaan parametrik global tanpa personalisasi komputasional dari data 2C?

## RQ2

Dengan episode, durasi, dan rekaman kalibrasi 2C pengguna yang sama, apakah sistem temporal berbasis **deep learning Conv1D dengan adaptor affine laten parameter-efficient** (maksimum 128 parameter khusus pengguna dalam candidate family yang dibekukan) memberikan keuntungan HCI yang bermakna secara praktis dibanding sistem parametrik berdimensi rendah, sehingga tambahan kompleksitas komputasi dan representasionalnya terjustifikasi?

## RQ3 — Sekunder

Seberapa besar gain dari personalisasi pada cabang learned dibanding baseline learned global, apakah differential personalization gain berbeda antar-keluarga sistem, dan bagaimana trade-off performa terhadap adaptation time, ukuran model, jumlah parameter yang berubah, serta latency?

---

# Kondisi Sistem yang Direncanakan

Eksperimen utama dirancang menggunakan empat kondisi.

## P0 — Parametrik Global

Sistem parametrik global tanpa personalisasi komputasional dari data kalibrasi pengguna.

Bentuk umum:

```text
v_t = B0 u_t + b0
```

---

## P2C — Parametrik Personalized

Sistem parametrik berdimensi rendah yang diadaptasi menggunakan kalibrasi singkat 2C pengguna.

Parameter personalisasi dirancang tetap kecil.

Rencana utama:

```text
2 × 2 mapping matrix
+
2 bias parameters
=
6 adapted parameters
```

Estimasi dilakukan menggunakan regularized least squares terhadap global prior.

Komponen seperti filtering dan dead-zone tidak dipersonalisasi.

---

## L0 — Learned Global

Sistem temporal global berbasis jaringan saraf Conv1D yang memproses urutan data accelerometer dan gyroscope.

Model ini tidak melakukan personalisasi khusus terhadap pengguna evaluasi.

Pengguna evaluasi harus merupakan pengguna yang tidak digunakan untuk melatih global model.

---

## L2C — Learned Personalized

Sistem temporal berbasis Conv1D dengan global encoder dan head yang dibekukan.

Personalisasi dilakukan menggunakan **affine latent adapter**:

```text
gamma
beta
```

Adapter diinisialisasi sebagai identity transformation.

Hanya parameter adapter yang berubah untuk pengguna baru.

Jumlah parameter khusus pengguna dibatasi maksimum:

```text
128 parameters
```

dalam candidate family yang telah dibekukan sebelum evaluasi final.

---

# Desain Kalibrasi 2C

Kalibrasi personalisasi menggunakan prosedur **2C** yang sama untuk P2C dan L2C.

Tujuannya adalah memastikan perbandingan dilakukan dengan beban kalibrasi pengguna yang setara.

Rencana arah center-out:

```text
R
UR
U
UL
L
DL
D
DR
```

Setiap arah kembali ke pusat.

Perkiraan:

```text
1 cycle ≈ 20 detik

2 cycles ≈ 40 detik
```

Rekaman mentah 2C yang sama digunakan oleh:

```text
P2C
dan
L2C
```

Dengan demikian, perbandingan tidak memberikan waktu atau jumlah data kalibrasi tambahan kepada salah satu keluarga sistem.

---

# Evaluasi HCI

Evaluasi utama direncanakan menggunakan tugas pointing multidirectional berbasis **Fitts' Law**.

Outcome primer:

```text
sequence-level Fitts throughput
```

Metrik tambahan dapat mencakup:

- movement time;
- error rate;
- effective target width;
- effective index of difficulty;
- throughput;
- adaptation time;
- model size;
- jumlah parameter yang berubah;
- computational latency.

Human evaluation dirancang sebagai **within-subject experiment** dengan counterbalancing kondisi.

---

# Kontras Utama

Kontras confirmatory yang direncanakan:

```text
RQ1:
P2C - P0
```

untuk menguji manfaat personalisasi parametrik.

```text
RQ2:
L2C - P2C
```

untuk menguji apakah kompleksitas sistem temporal berbasis deep learning memberikan keuntungan HCI yang bermakna dibanding sistem parametrik personalized dengan beban kalibrasi yang sama.

Analisis sekunder:

```text
L2C - L0
```

dan:

```text
ΔΔ =
(L2C - L0)
-
(P2C - P0)
```

untuk mengevaluasi differential personalization gain antar-keluarga sistem.

---

# Batas Durasi Eksperimen Manusia

Untuk mengurangi kelelahan pengguna:

```text
target active smartphone pointing ≤ 10 menit
```

Total kunjungan eksperimen dapat lebih panjang karena mencakup:

- penjelasan;
- informed consent;
- neutral hold;
- kalibrasi;
- transisi kondisi;
- istirahat;
- pointing task;
- penutupan.

Run engineering selama 25 menit bukan merupakan protokol pointing peserta.

---

# Arsitektur Sistem

Secara umum:

```text
Samsung Smartphone
        │
        │ Accelerometer + Gyroscope
        │
        ▼
Android Research Client
        │
        │ UDP DATA :5005
        ▼
PC Receiver
        │
        ├── preprocessing
        ├── clock mapping
        ├── cursor controller
        ├── parametric system
        └── temporal learned system
```

Clock synchronization menggunakan jalur terpisah:

```text
PC
│
│ UDP :5006
▼
Samsung

PC
▲
│ UDP :5006
│
Samsung
```

---

# Prinsip Timestamp

Waktu kedatangan paket di PC tidak digunakan sebagai pengganti timestamp sensor.

Android mempertahankan:

```text
SensorEvent.timestamp
callback_elapsed_ns
send_elapsed_ns
```

Clock synchronization menggunakan:

```text
Android:
SystemClock.elapsedRealtimeNanos()

PC:
time.monotonic_ns()
```

Model mapping:

```text
t_PC = alpha * t_phone + beta
```

Tujuan utamanya adalah membawa timestamp smartphone ke domain waktu monotonic PC yang sebanding.

---

# Status Engineering

## M0 — Validasi Device dan Sensor

### Status

```text
PASS pada engineering-development device
```

Perangkat pengembangan:

```text
Samsung SM-A066B
Android 16
```

Sensor:

```text
Accelerometer:
bmi3xy acc
Bosch

Gyroscope:
bmi3xy gyro
Bosch
```

Perangkat Oppo yang sebelumnya dipertimbangkan tidak digunakan karena gyroscope yang terdeteksi merupakan virtual/pseudo gyro.

---

# M1 — Akuisisi Sensor

### Status

```text
PASS / FROZEN
```

Akuisisi mempertahankan:

- `SensorEvent.timestamp`;
- accelerometer XYZ;
- gyroscope XYZ;
- `seq_global`;
- `seq_sensor`;
- callback monotonic timestamp;
- asynchronous local writer;
- dedicated sensor thread;
- metadata perangkat dan sensor.

Sampling request:

```text
10,000 microseconds
≈ 100 Hz
```

Pada engineering-development device, actual sampling terukur berada sekitar:

```text
99.5 Hz
```

Tidak ditemukan masalah utama pada:

- duplicate timestamp;
- non-monotonic timestamp;
- missing sequence.

Startup transient tetap diperlakukan sebagai karakteristik engineering yang perlu diketahui dan bukan alasan untuk memasangkan accelerometer dan gyroscope berdasarkan sequence number.

Accel dan gyro nantinya diselaraskan menggunakan timestamp pada common time grid.

Tag freeze:

```text
m1-sensor-freeze
```

---

# M2.1 — Real-Time UDP Streaming

### Status

```text
PASS
```

Jalur utama:

```text
Android
→ UDP port 5005
→ PC
```

UDP protocol v1 mempertahankan:

```text
DATA
protocol_version
session_id
record_name
seq_global
seq_sensor
sensor_type
sensor_ts_phone_ns
callback_elapsed_ns
send_elapsed_ns
x
y
z
accuracy
```

Transport menggunakan UDP karena penelitian membutuhkan respons interaktif dan packet loss dapat dihitung secara eksplisit melalui sequence number.

---

# M2.2 — Reliability Engineering

### Status

```text
ENGINEERING FREEZE pada Samsung SM-A066B
```

Receiver menghitung secara eksplisit:

- received packets;
- unique packets;
- missing packets;
- duplicate packets;
- out-of-order packets;
- packet loss;
- longest missing burst.

Android mencatat:

- packets sent;
- queue drops;
- UDP send errors.

Salah satu qualification run 25 menit yang lolos pada development device menunjukkan:

```text
sent       : 299225
unique recv: 299220
missing    : 5
duplicate  : 1
out-order  : 1
max burst  : 1
```

Engineering result tersebut hanya merupakan bukti untuk Samsung SM-A066B dan tidak otomatis berlaku pada perangkat penelitian final.

Tag:

```text
m2.2-reliability-freeze
```

---

# Cursor Engineering Preview

### Status

```text
IMPLEMENTED
```

Tersedia virtual cursor berbasis Pygame untuk kebutuhan engineering.

Preview ini **bukan** kondisi eksperimen peserta dan tidak diperlakukan sebagai P0/P2C/L0/L2C final.

Preview digunakan untuk memeriksa:

- axis mapping;
- direction sign;
- posture assumption;
- dead-zone;
- sensitivity;
- gain;
- stale-data handling;
- UDP input.

Mapping gyro pada development preview saat ini merupakan konfigurasi engineering dan masih harus diverifikasi kembali pada final device.

---

# M2.3 — Clock Synchronization

### Status

```text
IMPLEMENTED THROUGH M2.3-R1
FINAL FREEZE PENDING
```

Clock synchronization menggunakan port terpisah:

```text
UDP 5006
```

PC bertindak sebagai initiator dan smartphone sebagai responder.

Protocol:

```text
SYNC_REQ,1,<seq>,<t1_pc_ns>
```

Response:

```text
SYNC_RESP,1,<seq>,<t1_pc_ns>,<t2_phone_ns>,<t3_phone_ns>
```

Timestamp:

```text
t1 = PC sebelum send
t2 = phone setelah receive
t3 = phone sebelum response
t4 = PC setelah receive
```

Model:

```text
t_PC = alpha * t_phone + beta
```

---

# M2.3-R1 Microburst Scheduling

Desain background awal menggunakan:

```text
1 probe setiap 2 detik
```

Engineering run menunjukkan bahwa isolated probe dapat mengalami delay tinggi dan asymmetric scheduling.

R1 kemudian mengubah pola probing tanpa meningkatkan rata-rata traffic:

```text
startup:
30 probe @ 50 ms

background:
5 probe @ 50 ms
setiap 10 detik

shutdown:
30 probe @ 50 ms
```

Rata-rata background traffic tetap:

```text
0.5 probe / detik
```

Dari setiap scheduled background microburst dipilih:

```text
1 valid probe
dengan minimum delay_like_ns
```

Microburst grouping ditentukan berdasarkan scheduled sequence identity.

---

# Model Clock M2.3

Model affine menggunakan:

```text
centered OLS
with intercept
```

kemudian:

```text
residual calculation
↓
median + MAD screening
↓
final centered OLS
```

Konstanta robust screening:

```text
MAD_MULTIPLIER = 6.0
```

Nilai tersebut tidak boleh dituning terpisah untuk setiap run setelah hasilnya dilihat.

---

# Engineering Evidence M2.3

## R1 Run 2 Menit

Development device:

```text
Samsung SM-A066B
```

Hasil:

```text
sent probes      : 120
valid probes     : 120
response rate    : 100%

alpha            : 0.999990727656
skew_ppm         : -9.272344

absolute residual:
P50              : 0.180213 ms
P95              : 0.438176 ms
max              : 0.505786 ms

selected probes  : 12
inlier probes    : 12

first-half skew  : -5.919132 ppm
second-half skew : -4.379608 ppm
```

Selected-background delay diagnostic:

```text
P50 : 6.625554 ms
P95 : 8.790151 ms
max : 8.891892 ms
```

Low-delay endpoint diagnostic:

```text
endpoint skew        : -10.889498 ppm
startup best delay   : 6.316062 ms
shutdown best delay  : 6.323908 ms
```

---

## R1 Run 10 Menit dengan Representative IMU Load

Clock sync dijalankan bersamaan dengan streaming IMU UDP port 5005.

Hasil:

```text
sent probes      : 360
valid probes     : 360
response rate    : 100%

alpha            : 0.999987533175
skew_ppm         : -12.466825

selected probes  : 60
inlier probes    : 57

absolute residual:
P50              : 0.249263 ms
P95              : 0.916532 ms
max              : 1.480909 ms

first-half skew  : -10.832414 ppm
second-half skew : -12.499537 ppm
```

Nilai tersebut merupakan **engineering observations**, bukan universal acceptance thresholds.

Timing-quality threshold final belum dibekukan.

---

# Technical Invalid Run Policy

Run engineering tidak dihapus hanya karena hasilnya buruk.

Run hanya dapat diklasifikasikan sebagai **technical invalid** jika terjadi kegagalan infrastruktur yang jelas.

Contoh:

```text
m2_clock_02min_02
```

diklasifikasikan technical invalid karena laptop dan smartphone terhubung ke jaringan Wi-Fi yang berbeda.

Hasil:

```text
0 / 120 valid responses
```

Run tetap disimpan sebagai audit trail dan tidak digunakan dalam timing-quality characterization.

---

# Batas Klaim Latency

Penelitian ini tidak mengklaim **sensor-to-photon latency** tanpa instrumentation pada sisi display.

Komponen timing yang dapat dianalisis secara instrumented meliputi:

- callback delay pada smartphone;
- phone send delay;
- transport/scheduling age;
- PC receive time;
- preprocessing;
- inference;
- cursor update.

Istilah harus disesuaikan dengan komponen yang benar-benar diukur.

---

# Peralihan Perangkat Penelitian

Samsung SM-A066B dipertahankan sebagai:

```text
engineering-development device
```

Perangkat kandidat penelitian final:

```text
Samsung Galaxy A17 4G
```

Samsung A17 4G **belum dianggap qualified** hanya berdasarkan spesifikasi produk.

Perangkat harus melalui qualification ulang.

Urutan yang direncanakan:

```text
M0-A17
↓
device + sensor qualification

M1-A17
↓
sampling + timestamp validation

M2.1-A17
↓
UDP smoke test

M2.2-A17
↓
reliability characterization

M2.3-A17
↓
2 min
10 min
25 min

↓
timing-quality threshold freeze

↓
final engineering freeze

↓
pilot participant
```

Hasil A06 tidak akan diperlakukan sebagai bukti qualification A17.

---

# Prinsip Final Device

Setelah Samsung A17 4G lolos qualification, satu model smartphone final akan digunakan secara konsisten untuk penelitian manusia.

Tujuannya adalah menghindari **device effect** sebagai confounding factor.

Data peserta tidak direncanakan untuk dicampur antara:

```text
Samsung A06
dan
Samsung A17
```

---

# Struktur Repository

```text
android/
└── IMUResearchClient/
    └── aplikasi Android untuk:
        - akuisisi IMU
        - local logging
        - UDP streaming
        - clock-sync responder

pc/
├── receiver/
│   └── UDP receiver dan reliability accounting
│
├── cursor_preview/
│   └── engineering-only virtual cursor
│
└── clock_sync/
    ├── protocol.py
    ├── sync_client.py
    ├── clock_model.py
    ├── analyze_sync.py
    └── tests/

docs/
└── superpowers/
    ├── specs/
    └── plans/

validation_archive/
└── M1_SENSOR_FREEZE/
```

---

# Kebijakan Data Runtime

Data runtime engineering tidak disimpan sebagai source code Git.

Direktori yang dikecualikan antara lain:

```text
bench_data/
pc/receiver/logs/
participant_data/
data/participants/
```

Repository publik ditujukan untuk menyimpan:

- source code;
- automated tests;
- engineering design specification;
- implementation plan;
- selected non-participant validation evidence;
- dokumentasi penelitian.

Data peserta tidak akan dipublikasikan melalui repository ini tanpa prosedur dan pertimbangan etika yang sesuai.

---

# Pengujian Otomatis

Subsystem yang telah tersedia memiliki automated tests untuk:

- clock-sync protocol;
- affine clock model;
- robust fitting;
- scheduled microburst selection;
- sync client;
- analyzer;
- UDP receiver;
- cursor engineering preview.

Pada verifikasi branch M2.3 terbaru:

```text
65 Python tests passed
```

Android:

```text
testDebugUnitTest
BUILD SUCCESSFUL

assembleDebug
BUILD SUCCESSFUL
```

---

# Batas Engineering Freeze

M1 telah dibekukan.

M2.2 telah memiliki engineering freeze pada development device.

M2.3 **belum** diberi tag final:

```text
m2.3-clock-sync-freeze
```

Tag tersebut hanya akan dibuat setelah:

- Samsung A17 4G lolos qualification;
- final-device M2.3 2/10/25-minute bench selesai;
- timing-quality threshold ditentukan dan dibekukan;
- M2.2 regression tetap lolos;
- Android tests/build lolos;
- sistem siap menuju pilot manusia.

---

# Tahapan Penelitian

Roadmap tingkat tinggi:

```text
Engineering foundation
M0
M1
M2.1
M2.2
M2.3
        ↓
Samsung A17 4G qualification
        ↓
final acquisition / transport / timing freeze
        ↓
pointing-task implementation
        ↓
P0
P2C
        ↓
L0
L2C
        ↓
pilot
        ↓
independent human evaluation
        ↓
statistical analysis
        ↓
manuscript
        ↓
target publikasi minimal SINTA 2
```

---

# Batas Penelitian Manusia

Pengumpulan data manusia tidak dimulai sebelum:

- final device qualified;
- engineering configuration dibekukan;
- pointing task selesai;
- kondisi P0/P2C/L0/L2C siap;
- pilot protocol selesai;
- statistical analysis plan ditetapkan;
- persyaratan etik/institusional yang berlaku terpenuhi.

Pengguna evaluasi harus merupakan pengguna yang tidak digunakan untuk melatih global learned model.

---

# Reproducibility

Penelitian dirancang agar keputusan engineering penting dapat ditelusuri.

Repository mempertahankan:

- commit history;
- feature branches;
- Pull Requests;
- frozen milestone tags;
- automated tests;
- engineering specifications;
- implementation plans.

Hasil engineering yang gagal tidak dihapus hanya karena tidak mendukung hipotesis.

Technical-invalid run juga tetap dicatat dengan alasan eksplisit.

---

# Batas Klaim Penelitian

Repository ini belum menjadi bukti bahwa:

- personalisasi pasti meningkatkan throughput;
- deep learning pasti lebih baik daripada metode parametrik;
- L2C pasti lebih baik daripada P2C;
- sistem sudah siap untuk deployment;
- hasil engineering development device berlaku pada semua smartphone.

Kesimpulan tersebut hanya boleh dibuat setelah eksperimen dan analisis statistik selesai.

---

# Target Publikasi

Penelitian diarahkan menjadi artikel empiris di bidang:

- Sistem Informasi Cerdas;
- Human–Computer Interaction;
- Machine Learning / Deep Learning;
- Mobile Interaction;
- Intelligent User Interfaces.

Target publikasi:

```text
minimal jurnal nasional terakreditasi SINTA 2
```

Pemilihan jurnal final akan mempertimbangkan:

- scope jurnal;
- kesesuaian topik;
- kualitas metodologi;
- ketentuan penulis;
- format artikel;
- bahasa artikel;
- jadwal publikasi.

Bahasa README repository tidak menentukan peringkat SINTA. Bahasa naskah artikel final akan mengikuti author guidelines jurnal yang dipilih.

---

# Status Saat Ini

```text
M0 development-device qualification
DONE

M1 sensor acquisition
FROZEN

M2.1 UDP streaming
DONE

M2.2 reliability engineering
FROZEN on development device

Cursor Engineering Preview
DONE

M2.3 Clock Synchronization R1
IMPLEMENTED

M2.3 final freeze
PENDING A17 qualification

Samsung Galaxy A17 4G qualification
NEXT

Human participant pilot
NOT STARTED

Final evaluation
NOT STARTED

Deep-learning experimental branch
PLANNED / NOT FINALIZED
```

---

## Catatan

Repository ini merupakan bagian dari penelitian yang masih aktif dikembangkan.

Konfigurasi yang belum dibekukan dapat berubah berdasarkan engineering evidence, pilot results, dan methodological requirements.

Perubahan yang memengaruhi penelitian final akan didokumentasikan sebelum pengumpulan data peserta.
