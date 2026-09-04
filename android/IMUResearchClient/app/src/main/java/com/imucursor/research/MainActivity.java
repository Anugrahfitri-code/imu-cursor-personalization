package com.imucursor.research;

import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;

import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;

import android.util.Log;

import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;

import java.text.SimpleDateFormat;

import java.util.Date;
import java.util.Locale;

import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;


public class MainActivity extends AppCompatActivity
        implements SensorEventListener {

    // =========================================================
    // GENERAL CONFIGURATION
    // =========================================================

    private static final String TAG = "IMU_RESEARCH";

    /*
     * 10,000 microseconds = 10 ms
     * nominal request ~= 100 Hz
     */
    private static final int SAMPLING_PERIOD_US = 10000;


    // =========================================================
    // SENSOR
    // =========================================================

    private SensorManager sensorManager;

    private Sensor accelerometer;
    private Sensor gyroscope;


    // =========================================================
    // SENSOR THREAD
    // =========================================================

    /*
     * Sensor callback dibuat pada thread khusus,
     * bukan pada main/UI thread.
     */
    private HandlerThread sensorThread;
    private Handler sensorHandler;


    // =========================================================
    // WRITER THREAD
    // =========================================================

    /*
     * Sensor callback hanya memasukkan String row
     * ke queue.
     *
     * Disk I/O dilakukan pada writerThread terpisah.
     */
    private final LinkedBlockingQueue<String> writeQueue =
            new LinkedBlockingQueue<>();

    private Thread writerThread;

    private volatile boolean recording = false;
    private volatile boolean writerRunning = false;


    // =========================================================
    // FILE
    // =========================================================

    private BufferedWriter writer;

    private File currentFile;
    private File metadataFile;

    private String sessionId;
    private String recordName;


    // =========================================================
    // SEQUENCE COUNTERS
    // =========================================================

    private long globalSeq = 0;
    private long accelSeq = 0;
    private long gyroSeq = 0;


    // =========================================================
    // UI
    // =========================================================

    private TextView txtStatus;
    private TextView txtDevice;
    private TextView txtAccel;
    private TextView txtGyro;
    private TextView txtCount;
    private TextView txtFile;
    private TextView txtLastSession;

    private EditText editRecordName;

    private Button btnStart;
    private Button btnStop;
    private Button btnDeleteLast;


    // =========================================================
    // ON CREATE
    // =========================================================

    @Override
    protected void onCreate(Bundle savedInstanceState) {

        super.onCreate(savedInstanceState);

        setContentView(R.layout.activity_main);


        // -----------------------------------------------------
        // Bind UI
        // -----------------------------------------------------

        txtStatus =
                findViewById(R.id.txtStatus);

        txtDevice =
                findViewById(R.id.txtDevice);

        txtAccel =
                findViewById(R.id.txtAccel);

        txtGyro =
                findViewById(R.id.txtGyro);

        txtCount =
                findViewById(R.id.txtCount);

        txtFile =
                findViewById(R.id.txtFile);

        txtLastSession =
                findViewById(R.id.txtLastSession);

        editRecordName =
                findViewById(R.id.editRecordName);

        btnStart =
                findViewById(R.id.btnStart);

        btnStop =
                findViewById(R.id.btnStop);

        btnDeleteLast =
                findViewById(R.id.btnDeleteLast);


        // -----------------------------------------------------
        // Sensor manager
        // -----------------------------------------------------

        sensorManager =
                (SensorManager)
                        getSystemService(SENSOR_SERVICE);


        accelerometer =
                sensorManager.getDefaultSensor(
                        Sensor.TYPE_ACCELEROMETER
                );


        gyroscope =
                sensorManager.getDefaultSensor(
                        Sensor.TYPE_GYROSCOPE
                );


        // -----------------------------------------------------
        // Device information
        // -----------------------------------------------------

        txtDevice.setText(

                "Device: "
                        + Build.MANUFACTURER
                        + " "
                        + Build.MODEL

                        + "\nAndroid "
                        + Build.VERSION.RELEASE

                        + " | API "
                        + Build.VERSION.SDK_INT
        );


        // -----------------------------------------------------
        // Accelerometer information
        // -----------------------------------------------------

        if (accelerometer != null) {

            txtAccel.setText(

                    "Accelerometer: "
                            + accelerometer.getName()

                            + "\nVendor: "
                            + accelerometer.getVendor()
            );

        } else {

            txtAccel.setText(
                    "Accelerometer: NOT FOUND"
            );
        }


        // -----------------------------------------------------
        // Gyroscope information
        // -----------------------------------------------------

        if (gyroscope != null) {

            txtGyro.setText(

                    "Gyroscope: "
                            + gyroscope.getName()

                            + "\nVendor: "
                            + gyroscope.getVendor()
            );

        } else {

            txtGyro.setText(
                    "Gyroscope: NOT FOUND"
            );
        }


        // -----------------------------------------------------
        // Sensor thread
        // -----------------------------------------------------

        sensorThread =
                new HandlerThread(
                        "IMUSensorThread"
                );

        sensorThread.start();


        sensorHandler =
                new Handler(
                        sensorThread.getLooper()
                );


        // -----------------------------------------------------
        // Buttons
        // -----------------------------------------------------

        btnStart.setOnClickListener(
                v -> startRecording()
        );


        btnStop.setOnClickListener(
                v -> stopRecording()
        );


        btnDeleteLast.setOnClickListener(
                v -> confirmDeleteLastSession()
        );


        // -----------------------------------------------------
        // Initial UI state
        // -----------------------------------------------------

        txtStatus.setText("READY");

        updateLastSessionUI();
        updateDeleteButtonState();
    }


    // =========================================================
    // START RECORDING
    // =========================================================

    private void startRecording() {

        if (recording) {

            return;
        }


        // -----------------------------------------------------
        // Sensor validation
        // -----------------------------------------------------

        if (accelerometer == null
                || gyroscope == null) {

            txtStatus.setText(
                    "ERROR: Required sensors unavailable"
            );

            return;
        }


        // -----------------------------------------------------
        // Recording name validation
        // -----------------------------------------------------

        String inputName =
                editRecordName
                        .getText()
                        .toString()
                        .trim();


        if (inputName.isEmpty()) {

            editRecordName.setError(
                    "Recording name wajib diisi"
            );

            editRecordName.requestFocus();

            return;
        }


        recordName =
                sanitizeRecordName(
                        inputName
                );


        if (recordName.isEmpty()) {

            editRecordName.setError(
                    "Nama recording tidak valid"
            );

            editRecordName.requestFocus();

            return;
        }


        // -----------------------------------------------------
        // Generate session ID
        // -----------------------------------------------------

        sessionId =
                new SimpleDateFormat(

                        "yyyyMMdd_HHmmss_SSS",

                        Locale.US

                ).format(
                        new Date()
                );


        // -----------------------------------------------------
        // Session directory
        // -----------------------------------------------------

        File directory =
                getSessionsDirectory();


        if (!directory.exists()) {

            boolean created =
                    directory.mkdirs();


            Log.i(

                    TAG,

                    "Session directory created="
                            + created
            );
        }


        // -----------------------------------------------------
        // File suffix
        // -----------------------------------------------------

        /*
         * Example:
         *
         * stationary_01_20260904_221109_906
         */

        String suffix =
                recordName
                        + "_"
                        + sessionId;


        // -----------------------------------------------------
        // Create files
        // -----------------------------------------------------

        currentFile =
                new File(

                        directory,

                        "imu_"
                                + suffix
                                + ".csv"
                );


        metadataFile =
                new File(

                        directory,

                        "meta_"
                                + suffix
                                + ".txt"
                );


        // -----------------------------------------------------
        // Reset counters
        // -----------------------------------------------------

        globalSeq = 0;
        accelSeq = 0;
        gyroSeq = 0;

        writeQueue.clear();


        // -----------------------------------------------------
        // Create CSV writer
        // -----------------------------------------------------

        try {

            writer =
                    new BufferedWriter(

                            new FileWriter(
                                    currentFile
                            )
                    );


            writer.write(

                    "session_id,"
                            + "record_name,"
                            + "seq_global,"
                            + "seq_sensor,"
                            + "sensor_type,"
                            + "sensor_ts_phone_ns,"
                            + "callback_elapsed_ns,"
                            + "x,"
                            + "y,"
                            + "z,"
                            + "accuracy\n"
            );


            writer.flush();


        } catch (IOException e) {

            Log.e(

                    TAG,

                    "Cannot create CSV",

                    e
            );


            txtStatus.setText(
                    "ERROR creating CSV"
            );


            return;
        }


        // -----------------------------------------------------
        // Metadata
        // -----------------------------------------------------

        writeSessionMetadata();


        // -----------------------------------------------------
        // Start writer thread
        // -----------------------------------------------------

        writerRunning = true;


        writerThread =
                new Thread(

                        this::writerLoop,

                        "IMUWriterThread"
                );


        writerThread.start();


        // -----------------------------------------------------
        // Enable acquisition
        // -----------------------------------------------------

        recording = true;


        boolean accelRegistered =
                sensorManager.registerListener(

                        this,

                        accelerometer,

                        SAMPLING_PERIOD_US,

                        0,

                        sensorHandler
                );


        boolean gyroRegistered =
                sensorManager.registerListener(

                        this,

                        gyroscope,

                        SAMPLING_PERIOD_US,

                        0,

                        sensorHandler
                );


        // -----------------------------------------------------
        // Registration check
        // -----------------------------------------------------

        if (!accelRegistered
                || !gyroRegistered) {

            Log.e(

                    TAG,

                    "Sensor registration failed."
                            + " ACC="
                            + accelRegistered

                            + " GYRO="
                            + gyroRegistered
            );


            txtStatus.setText(
                    "ERROR: Sensor registration failed"
            );


            stopRecording();

            return;
        }


        // -----------------------------------------------------
        // Logs
        // -----------------------------------------------------

        Log.i(

                TAG,

                "Recording name="
                        + recordName
        );


        Log.i(

                TAG,

                "Session ID="
                        + sessionId
        );


        Log.i(

                TAG,

                "ACC registered="
                        + accelRegistered
        );


        Log.i(

                TAG,

                "GYRO registered="
                        + gyroRegistered
        );


        Log.i(

                TAG,

                "Sampling request="
                        + SAMPLING_PERIOD_US
                        + " us"
        );


        // -----------------------------------------------------
        // UI
        // -----------------------------------------------------

        txtStatus.setText(

                "RECORDING\n"
                        + recordName
        );


        txtCount.setText(

                "Total: 0"
                        + "\nACC: 0"
                        + "\nGYRO: 0"
        );


        txtFile.setText(

                "File:\n"
                        + currentFile
                        .getAbsolutePath()
        );


        editRecordName.setEnabled(false);

        btnStart.setEnabled(false);

        btnStop.setEnabled(true);

        btnDeleteLast.setEnabled(false);
    }


    // =========================================================
    // SENSOR CALLBACK
    // =========================================================

    @Override
    public void onSensorChanged(
            SensorEvent event) {


        if (!recording) {

            return;
        }


        // -----------------------------------------------------
        // Callback timestamp
        // -----------------------------------------------------

        long callbackElapsedNs =
                SystemClock
                        .elapsedRealtimeNanos();


        /*
         * Primary hardware-related timestamp.
         */
        long sensorTimestampNs =
                event.timestamp;


        // -----------------------------------------------------
        // Sensor identification
        // -----------------------------------------------------

        String sensorType;

        long sensorSeq;


        if (event.sensor.getType()
                == Sensor.TYPE_ACCELEROMETER) {


            accelSeq++;

            sensorSeq =
                    accelSeq;

            sensorType =
                    "ACC";


        } else if (event.sensor.getType()
                == Sensor.TYPE_GYROSCOPE) {


            gyroSeq++;

            sensorSeq =
                    gyroSeq;

            sensorType =
                    "GYRO";


        } else {

            return;
        }


        // -----------------------------------------------------
        // Global sequence
        // -----------------------------------------------------

        globalSeq++;


        // -----------------------------------------------------
        // Sensor values
        // -----------------------------------------------------

        float x =
                event.values[0];

        float y =
                event.values[1];

        float z =
                event.values[2];


        // -----------------------------------------------------
        // CSV row
        // -----------------------------------------------------

        String row =

                sessionId
                        + ","

                        + recordName
                        + ","

                        + globalSeq
                        + ","

                        + sensorSeq
                        + ","

                        + sensorType
                        + ","

                        + sensorTimestampNs
                        + ","

                        + callbackElapsedNs
                        + ","

                        + x
                        + ","

                        + y
                        + ","

                        + z
                        + ","

                        + event.accuracy

                        + "\n";


        // -----------------------------------------------------
        // Queue only
        // -----------------------------------------------------

        writeQueue.offer(
                row
        );


        // -----------------------------------------------------
        // UI update
        // -----------------------------------------------------

        if (globalSeq % 200 == 0) {


            long total =
                    globalSeq;


            long acc =
                    accelSeq;


            long gyro =
                    gyroSeq;


            runOnUiThread(() ->

                    txtCount.setText(

                            "Total: "
                                    + total

                                    + "\nACC: "
                                    + acc

                                    + "\nGYRO: "
                                    + gyro
                    )
            );
        }
    }


    // =========================================================
    // WRITER LOOP
    // =========================================================

    private void writerLoop() {


        long writtenRows = 0;


        try {


            while (writerRunning
                    || !writeQueue.isEmpty()) {


                String row =
                        writeQueue.poll(

                                100,

                                TimeUnit.MILLISECONDS
                        );


                if (row == null) {

                    continue;
                }


                writer.write(
                        row
                );


                writtenRows++;


                if (writtenRows % 1000 == 0) {


                    writer.flush();


                    Log.i(

                            TAG,

                            "Written rows="
                                    + writtenRows

                                    + " queue="
                                    + writeQueue.size()
                    );
                }
            }


            writer.flush();


        } catch (IOException e) {


            Log.e(

                    TAG,

                    "Writer thread I/O error",

                    e
            );


        } catch (InterruptedException e) {


            Thread.currentThread()
                    .interrupt();


            Log.e(

                    TAG,

                    "Writer thread interrupted",

                    e
            );
        }
    }


    // =========================================================
    // STOP RECORDING
    // =========================================================

    private void stopRecording() {


        if (!recording) {

            return;
        }


        // -----------------------------------------------------
        // Stop acquisition
        // -----------------------------------------------------

        recording = false;


        sensorManager.unregisterListener(
                this
        );


        // -----------------------------------------------------
        // Stop writer AFTER queue emptied
        // -----------------------------------------------------

        writerRunning = false;


        if (writerThread != null) {


            try {


                writerThread.join(
                        5000
                );


            } catch (
                    InterruptedException e
            ) {


                Thread.currentThread()
                        .interrupt();
            }
        }


        // -----------------------------------------------------
        // Close file
        // -----------------------------------------------------

        try {


            if (writer != null) {


                writer.flush();

                writer.close();

                writer = null;
            }


        } catch (IOException e) {


            Log.e(

                    TAG,

                    "Error closing CSV",

                    e
            );
        }


        // -----------------------------------------------------
        // Save values before reset
        // -----------------------------------------------------

        long finalGlobal =
                globalSeq;


        long finalAccel =
                accelSeq;


        long finalGyro =
                gyroSeq;


        String finishedName =
                recordName;


        // -----------------------------------------------------
        // UI
        // -----------------------------------------------------

        txtStatus.setText(

                "STOPPED\n"
                        + finishedName
        );


        txtCount.setText(

                "Total: "
                        + finalGlobal

                        + "\nACC: "
                        + finalAccel

                        + "\nGYRO: "
                        + finalGyro
        );


        editRecordName.setEnabled(true);

        editRecordName.setText("");

        btnStart.setEnabled(true);

        btnStop.setEnabled(false);


        // -----------------------------------------------------
        // Update last session
        // -----------------------------------------------------

        updateLastSessionUI();

        updateDeleteButtonState();


        // -----------------------------------------------------
        // Log
        // -----------------------------------------------------

        Log.i(

                TAG,

                "Session stopped"
                        + " name="
                        + finishedName

                        + " Total="
                        + finalGlobal

                        + " ACC="
                        + finalAccel

                        + " GYRO="
                        + finalGyro

                        + " remainingQueue="
                        + writeQueue.size()
        );


        Toast.makeText(

                this,

                "Recording tersimpan: "
                        + finishedName,

                Toast.LENGTH_SHORT

        ).show();
    }


    // =========================================================
    // SESSION METADATA
    // =========================================================

    private void writeSessionMetadata() {


        long startElapsedNs =
                SystemClock
                        .elapsedRealtimeNanos();


        try (
                BufferedWriter metadataWriter =

                        new BufferedWriter(

                                new FileWriter(
                                        metadataFile
                                )
                        )
        ) {


            metadataWriter.write(

                    "session_id="
                            + sessionId
                            + "\n"
            );


            metadataWriter.write(

                    "record_name="
                            + recordName
                            + "\n"
            );


            metadataWriter.write(

                    "manufacturer="
                            + Build.MANUFACTURER
                            + "\n"
            );


            metadataWriter.write(

                    "model="
                            + Build.MODEL
                            + "\n"
            );


            metadataWriter.write(

                    "android_version="
                            + Build.VERSION.RELEASE
                            + "\n"
            );


            metadataWriter.write(

                    "api_level="
                            + Build.VERSION.SDK_INT
                            + "\n"
            );


            metadataWriter.write(

                    "requested_sampling_us="
                            + SAMPLING_PERIOD_US
                            + "\n"
            );


            metadataWriter.write(

                    "requested_sampling_hz="
                            + (
                            1_000_000.0
                                    / SAMPLING_PERIOD_US
                    )
                            + "\n"
            );


            metadataWriter.write(

                    "session_start_elapsed_ns="
                            + startElapsedNs
                            + "\n"
            );


            // -------------------------------------------------
            // Accelerometer metadata
            // -------------------------------------------------

            if (accelerometer != null) {


                metadataWriter.write(

                        "accelerometer_name="
                                + accelerometer
                                .getName()
                                + "\n"
                );


                metadataWriter.write(

                        "accelerometer_vendor="
                                + accelerometer
                                .getVendor()
                                + "\n"
                );


                metadataWriter.write(

                        "accelerometer_version="
                                + accelerometer
                                .getVersion()
                                + "\n"
                );


                metadataWriter.write(

                        "accelerometer_resolution="
                                + accelerometer
                                .getResolution()
                                + "\n"
                );


                metadataWriter.write(

                        "accelerometer_max_range="
                                + accelerometer
                                .getMaximumRange()
                                + "\n"
                );


                metadataWriter.write(

                        "accelerometer_min_delay_us="
                                + accelerometer
                                .getMinDelay()
                                + "\n"
                );
            }


            // -------------------------------------------------
            // Gyroscope metadata
            // -------------------------------------------------

            if (gyroscope != null) {


                metadataWriter.write(

                        "gyroscope_name="
                                + gyroscope
                                .getName()
                                + "\n"
                );


                metadataWriter.write(

                        "gyroscope_vendor="
                                + gyroscope
                                .getVendor()
                                + "\n"
                );


                metadataWriter.write(

                        "gyroscope_version="
                                + gyroscope
                                .getVersion()
                                + "\n"
                );


                metadataWriter.write(

                        "gyroscope_resolution="
                                + gyroscope
                                .getResolution()
                                + "\n"
                );


                metadataWriter.write(

                        "gyroscope_max_range="
                                + gyroscope
                                .getMaximumRange()
                                + "\n"
                );


                metadataWriter.write(

                        "gyroscope_min_delay_us="
                                + gyroscope
                                .getMinDelay()
                                + "\n"
                );
            }


        } catch (IOException e) {


            Log.e(

                    TAG,

                    "Cannot write metadata",

                    e
            );
        }
    }


    // =========================================================
    // RECORD NAME SANITIZATION
    // =========================================================

    private String sanitizeRecordName(
            String input) {


        String cleaned =
                input
                        .trim()
                        .toLowerCase(
                                Locale.US
                        );


        /*
         * Spaces become underscore.
         */
        cleaned =
                cleaned.replaceAll(
                        "\\s+",
                        "_"
                );


        /*
         * Keep only:
         * a-z
         * 0-9
         * _
         * -
         */
        cleaned =
                cleaned.replaceAll(
                        "[^a-z0-9_-]",
                        ""
                );


        /*
         * Avoid many underscores.
         */
        cleaned =
                cleaned.replaceAll(
                        "_+",
                        "_"
                );


        return cleaned;
    }


    // =========================================================
    // SESSION DIRECTORY
    // =========================================================

    private File getSessionsDirectory() {


        return new File(

                getExternalFilesDir(null),

                "sessions"
        );
    }


    // =========================================================
    // FIND LAST IMU FILE
    // =========================================================

    private File findLatestImuFile() {


        File directory =
                getSessionsDirectory();


        if (!directory.exists()) {

            return null;
        }


        File[] files =
                directory.listFiles();


        if (files == null
                || files.length == 0) {

            return null;
        }


        File latestFile =
                null;


        for (File file : files) {


            String name =
                    file.getName();


            if (!name.startsWith("imu_")
                    || !name.endsWith(".csv")) {

                continue;
            }


            if (latestFile == null
                    || file.lastModified()
                    > latestFile.lastModified()) {


                latestFile =
                        file;
            }
        }


        return latestFile;
    }


    // =========================================================
    // MATCHING META FILE
    // =========================================================

    private File findMatchingMetadataFile(
            File imuFile) {


        if (imuFile == null) {

            return null;
        }


        String imuName =
                imuFile.getName();


        /*
         * imu_stationary_01_XXXX.csv
         *
         * ->
         *
         * stationary_01_XXXX
         */

        String suffix =
                imuName.substring(

                        "imu_".length(),

                        imuName.length()
                                - ".csv".length()
                );


        return new File(

                getSessionsDirectory(),

                "meta_"
                        + suffix
                        + ".txt"
        );
    }


    // =========================================================
    // READ RECORD NAME FROM METADATA
    // =========================================================

    private String readRecordNameFromMetadata(
            File metaFile) {


        if (metaFile == null
                || !metaFile.exists()) {

            return "unknown";
        }


        try (
                BufferedReader reader =

                        new BufferedReader(

                                new FileReader(
                                        metaFile
                                )
                        )
        ) {


            String line;


            while (
                    (line = reader.readLine())
                            != null
            ) {


                if (line.startsWith(
                        "record_name="
                )) {


                    return line.substring(
                            "record_name=".length()
                    );
                }
            }


        } catch (IOException e) {


            Log.e(

                    TAG,

                    "Cannot read metadata",

                    e
            );
        }


        return "unknown";
    }


    // =========================================================
    // DELETE BUTTON STATE
    // =========================================================

    private void updateDeleteButtonState() {


        if (btnDeleteLast == null) {

            return;
        }


        if (recording) {


            btnDeleteLast.setEnabled(
                    false
            );


            return;
        }


        File latestFile =
                findLatestImuFile();


        btnDeleteLast.setEnabled(
                latestFile != null
        );
    }


    // =========================================================
    // UPDATE LAST SESSION UI
    // =========================================================

    private void updateLastSessionUI() {


        File imuFile =
                findLatestImuFile();


        if (imuFile == null) {


            txtLastSession.setText(
                    "Last session: -"
            );


            return;
        }


        File metaFile =
                findMatchingMetadataFile(
                        imuFile
                );


        String lastRecordName =
                readRecordNameFromMetadata(
                        metaFile
                );


        txtLastSession.setText(

                "Last session:\n"
                        + lastRecordName

                        + "\n"

                        + imuFile.getName()
        );
    }


    // =========================================================
    // DELETE CONFIRMATION
    // =========================================================

    private void confirmDeleteLastSession() {


        if (recording) {


            txtStatus.setText(
                    "Cannot delete while recording"
            );


            return;
        }


        File imuFile =
                findLatestImuFile();


        if (imuFile == null) {


            txtStatus.setText(
                    "No recording available"
            );


            updateDeleteButtonState();


            return;
        }


        File metaFile =
                findMatchingMetadataFile(
                        imuFile
                );


        String lastRecordName =
                readRecordNameFromMetadata(
                        metaFile
                );


        new AlertDialog.Builder(
                this
        )

                .setTitle(
                        "Delete Last Recording?"
                )

                .setMessage(

                        "Recording name:\n"
                                + lastRecordName

                                + "\n\nCSV:\n"
                                + imuFile.getName()

                                + "\n\nMetadata:\n"
                                + (
                                metaFile != null
                                        ? metaFile.getName()
                                        : "-"
                        )

                                + "\n\n"
                                + "File akan dihapus permanen."
                )

                .setNegativeButton(

                        "CANCEL",

                        null
                )

                .setPositiveButton(

                        "DELETE",

                        (dialog, which) ->

                                deleteSession(

                                        lastRecordName,

                                        imuFile,

                                        metaFile
                                )
                )

                .show();
    }


    // =========================================================
    // DELETE SESSION
    // =========================================================

    private void deleteSession(
            String deletedRecordName,
            File imuFile,
            File metaFile) {


        writeDeletionAudit(

                deletedRecordName,

                imuFile,

                metaFile
        );


        boolean imuDeleted =
                true;


        boolean metaDeleted =
                true;


        if (imuFile != null
                && imuFile.exists()) {


            imuDeleted =
                    imuFile.delete();
        }


        if (metaFile != null
                && metaFile.exists()) {


            metaDeleted =
                    metaFile.delete();
        }


        if (imuDeleted
                && metaDeleted) {


            txtStatus.setText(

                    "DELETED\n"
                            + deletedRecordName
            );


            txtFile.setText(
                    "File: -"
            );


            txtCount.setText(

                    "Total: 0"
                            + "\nACC: 0"
                            + "\nGYRO: 0"
            );


            Toast.makeText(

                    this,

                    "Recording deleted: "
                            + deletedRecordName,

                    Toast.LENGTH_SHORT

            ).show();


            Log.i(

                    TAG,

                    "Session deleted: "
                            + deletedRecordName
            );


        } else {


            txtStatus.setText(

                    "ERROR: Could not delete all files"
            );


            Log.e(

                    TAG,

                    "Delete failed."
                            + " IMU="
                            + imuDeleted

                            + " META="
                            + metaDeleted
            );
        }


        updateLastSessionUI();

        updateDeleteButtonState();
    }


    // =========================================================
    // DELETION AUDIT
    // =========================================================

    private void writeDeletionAudit(
            String deletedRecordName,
            File imuFile,
            File metaFile) {


        File directory =
                getSessionsDirectory();


        if (!directory.exists()) {

            directory.mkdirs();
        }


        File auditFile =
                new File(

                        directory,

                        "deletion_audit.csv"
                );


        boolean newFile =
                !auditFile.exists();


        try (
                BufferedWriter auditWriter =

                        new BufferedWriter(

                                new FileWriter(

                                        auditFile,

                                        true
                                )
                        )
        ) {


            if (newFile) {


                auditWriter.write(

                        "deleted_at,"
                                + "record_name,"
                                + "imu_file,"
                                + "metadata_file\n"
                );
            }


            String deletedAt =
                    new SimpleDateFormat(

                            "yyyy-MM-dd'T'HH:mm:ss.SSS",

                            Locale.US

                    ).format(
                            new Date()
                    );


            auditWriter.write(

                    deletedAt
                            + ","

                            + deletedRecordName
                            + ","

                            + (
                            imuFile != null
                                    ? imuFile.getName()
                                    : ""
                    )
                            + ","

                            + (
                            metaFile != null
                                    ? metaFile.getName()
                                    : ""
                    )

                            + "\n"
            );


            auditWriter.flush();


        } catch (IOException e) {


            Log.e(

                    TAG,

                    "Cannot write deletion audit",

                    e
            );
        }
    }


    // =========================================================
    // ACCURACY CALLBACK
    // =========================================================

    @Override
    public void onAccuracyChanged(
            Sensor sensor,
            int accuracy) {


        Log.i(

                TAG,

                "Accuracy: "
                        + sensor.getName()

                        + " = "
                        + accuracy
        );
    }


    // =========================================================
    // ACTIVITY LIFECYCLE
    // =========================================================

    @Override
    protected void onPause() {

        super.onPause();


        /*
         * Untuk bench logger:
         * kalau app keluar foreground ketika recording,
         * recording dihentikan secara aman.
         */
        if (recording) {

            stopRecording();
        }
    }


    @Override
    protected void onDestroy() {

        super.onDestroy();


        if (recording) {

            stopRecording();
        }


        if (sensorThread != null) {

            sensorThread.quitSafely();
        }
    }
}