# Perbaikan audit Tahap 2.5 — 19 September 2026

Status: perbaikan perangkat lunak untuk ditinjau; bukan final freeze penelitian.

Basis kode: `7eecf7685fbf9f051d745f3d8aafdba060d0c7b2`.
Branch kerja: `fix/stage25-audit-hardening`.

## Perubahan kontrak dan perilaku

1. **Kualifikasi kandidat.** Laporan baru menggunakan versi
   `stage2.5-candidate-qualification-v2.0`. Sembilan dimensi diuji melalui
   komponen produksi dengan keluaran yang diharapkan secara independen.
   Kegagalan fixture menjadi kegagalan gate kandidat. Perbandingan yang belum
   memiliki implementasi diberi `NOT_IMPLEMENTED`, bukan `PASS`.
2. **Kausalitas.** Kualifikasi mengubah nilai sensor setelah beberapa waktu
   potong, membandingkan keluaran sebelumnya, dan memastikan keluaran sesudahnya
   benar-benar berubah. Ini bukti pengujian terbatas, bukan pembuktian untuk
   seluruh masukan. Label supervisi tidak dianggap sebagai fitur sensor online.
3. **Inisialisasi bias.** Builder hanya menerbitkan baris dengan
   `grid_pc_time_ns > bias_correction.window_end_pc_ns`. Data mentah pada interval
   bias tetap digunakan untuk estimasi. Jika tidak ada keluaran setelah interval
   tersebut, build ditolak. Jumlah baris, indeks, keluaran filter, dan hash dapat
   berubah dibanding hasil lama.
4. **Frekuensi.** `grid_frequency_hz` harus sama dengan
   `1_000_000_000 / grid_interval_ns`; frekuensi filter harus cocok dengan grid.
   Konfigurasi minimal harus menyebut sumber mapped sensor, referensi, dan clock.
5. **Asal artefak.** Builder numerik tetap menerima data dalam memori yang
   dipercaya pemanggil. Gunakan `build_stage25_from_artifacts` dari
   `pc.experiment.preprocessing.artifacts` untuk verifikasi berkas, hash, potongan
   sumber kalibrasi, pemetaan clock, dan identitas. Verifikasi berkas tidak
   membuktikan bahwa data berasal dari partisipan nyata atau disetujui etik.
6. **Integritas sesi.** Inventaris checksum harus lengkap, tidak kosong, dan
   tidak memiliki entri ganda. Sumber bukti harus menggunakan jalur relatif
   yang aman serta hash yang cocok. Finalisasi tidak boleh mengganti baseline
   checksum lama yang sudah tidak valid. Penambahan berkas pada sesi yang sudah
   ditutup dengan checksum akan membuat pemeriksaan inventaris gagal.
7. **Manifest sesi.** Metadata device/display serta pasangan jalur dan hash
   Android/clock wajib diisi sesuai kontrak. Sesi tertutup harus berisi event
   trial atau kalibrasi; kondisi yang teramati harus tercantum dalam
   `condition_order`. Sesi pengembangan kalibrasi tetap diperbolehkan; tidak
   diberlakukan kewajiban empat kondisi pada semua jenis sesi.
8. **Clock.** Evaluator menghitung ulang model dari empat timestamp probe dan
   membandingkan parameter serta diagnostik tersimpan. Gate numerik memakai
   hasil rekonstruksi. API `verify_clock_artifacts` hanya memeriksa bukti clock;
   kelulusan device, transport, dan keseluruhan sesi memerlukan evaluator sesi.

## Versi dan bukti lama

Skema baris common grid tetap versi 1.0; hasil numerik dan jumlah baris dapat
berubah karena koreksi batas bias. Pengetatan manifest menerapkan kontrak 1.0
yang sudah ada. Laporan kualifikasi baru mempunyai versi tersendiri.

Simpan keluaran kualifikasi baru pada direktori baru. Penulis laporan menolak
menimpa bukti lama yang berbeda. Jangan mengganti hash, keputusan historis,
atau hasil konfirmasi v1.1 secara retroaktif. Konfigurasi yang dipakai kembali
untuk freeze harus mempunyai identitas/versi derivasi baru dan
`functional_commit` yang menunjuk commit implementasi setelah perbaikan ini
diintegrasikan.

Dokumen keputusan v1.0 pada unggahan memiliki perubahan lokal yang berbeda
dari HEAD. Paket ini menambahkan catatan audit tanpa menimpa dokumen tersebut.

## Batas hasil dan pekerjaan berikutnya

- Tes perangkat lunak dan microfixture sintetis tidak menggantikan Task 17
  (kualifikasi sintetis end-to-end final) atau Task 18 (regresi, pencatatan
  evidence, dan freeze). Keduanya belum ditutup oleh catatan ini.
- Kausalitas berdasarkan timestamp sensor yang telah dipetakan tidak menjamin
  data sudah tersedia pada PC ketika prediksi real-time dijalankan. Uji
  ketersediaan data dan latensi penerimaan harus memakai waktu kedatangan PC.
- Residual model clock mengukur kecocokan terhadap estimasi waktu dari probe;
  residual kecil tidak membuktikan galat waktu absolut kecil jika delay jaringan
  asimetris. Ambang historis tidak diubah dalam paket ini.
- Audit Android mengenai STOP/drain queue, persistensi, dan lifecycle masih
  memerlukan perbaikan serta pengujian pada perangkat fisik. Tidak ada klaim
  build atau runtime Android telah lulus.
- P0, P2C, L0, L2C, evaluasi Fitts, pilot partisipan, serta pemilihan parameter
  berdasarkan performa partisipan tidak termasuk paket ini.

Perintah regresi dari akar proyek:

```text
python -m pytest pc -q
git diff --check
```
