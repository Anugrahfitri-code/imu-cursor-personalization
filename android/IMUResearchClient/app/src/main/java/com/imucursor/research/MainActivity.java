package com.imucursor.research;

import android.Manifest;
import android.content.ComponentName;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.pm.PackageManager;
import android.hardware.Sensor;
import android.hardware.SensorManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
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
import java.net.InetAddress;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * UI/controller for the research client.
 *
 * Sensor acquisition is intentionally NOT owned by this Activity. It is
 * delegated to RecordingService so leaving the screen, pressing Home, or
 * removing the task does not become a recording stop condition.
 */
public class MainActivity extends AppCompatActivity {

    private static final String TAG = "IMU_RESEARCH";
    private static final int NOTIFICATION_PERMISSION_REQUEST = 1001;

    private final ClockSyncController clockSyncController =
            new ClockSyncController();

    private Sensor accelerometer;
    private Sensor gyroscope;

    private volatile boolean starting = false;
    private volatile boolean recording = false;
    private volatile boolean stopping = false;

    private RecordingService recordingService;
    private boolean recordingServiceBound = false;
    private boolean recordingServiceBindingActive = false;
    private RecordingService.RecordingSnapshot lastRecordingSnapshot;

    private Handler uiTimerHandler;
    private boolean timerTickerActive = false;

    private TextView txtStatus;
    private TextView txtDevice;
    private TextView txtAccel;
    private TextView txtGyro;
    private TextView txtNetwork;
    private TextView txtTimer;
    private TextView txtCount;
    private TextView txtNetworkCount;
    private TextView txtFile;
    private TextView txtLastSession;

    private EditText editRecordName;
    private EditText editPcIp;
    private EditText editPcPort;

    private Button btnStart;
    private Button btnStop;
    private Button btnDeleteLast;

    private String activeRecordName = "";

    private final RecordingService.Listener recordingListener =
            this::renderRecordingSnapshot;

    private final ServiceConnection recordingServiceConnection =
            new ServiceConnection() {
                @Override
                public void onServiceConnected(
                        ComponentName name,
                        IBinder service
                ) {
                    RecordingService.LocalBinder localBinder =
                            (RecordingService.LocalBinder) service;

                    recordingService = localBinder.getService();
                    recordingServiceBound = true;
                    recordingService.setListener(recordingListener);
                    renderRecordingSnapshot(
                            recordingService.getSnapshot()
                    );
                }

                @Override
                public void onServiceDisconnected(
                        ComponentName name
                ) {
                    boolean wasActive = starting || recording || stopping;

                    recordingServiceBound = false;
                    recordingService = null;
                    starting = false;
                    recording = false;
                    stopping = false;

                    if (wasActive) {
                        txtStatus.setText(
                                "SERVICE DISCONNECTED\n"
                                        + "Recording may have been interrupted"
                        );
                        setInputsEnabled(true);
                        btnStart.setEnabled(true);
                        btnStop.setEnabled(false);
                        updateDeleteButtonState();
                    }
                }
            };

    private final Runnable timerRunnable = new Runnable() {
        @Override
        public void run() {
            if (!timerTickerActive) {
                return;
            }

            if (recordingServiceBound && recordingService != null) {
                RecordingService.RecordingSnapshot snapshot =
                        recordingService.getSnapshot();
                lastRecordingSnapshot = snapshot;
                updateTimerText(snapshot.elapsedMs);
            } else if (recording
                    && lastRecordingSnapshot != null
                    && lastRecordingSnapshot.recording
                    && lastRecordingSnapshot.startElapsedRealtimeMs > 0L) {

                long elapsedMs = Math.max(
                        0L,
                        SystemClock.elapsedRealtime()
                                - lastRecordingSnapshot.startElapsedRealtimeMs
                );
                updateTimerText(elapsedMs);
            }

            if (uiTimerHandler != null) {
                uiTimerHandler.postDelayed(this, 250L);
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        uiTimerHandler = new Handler(Looper.getMainLooper());

        // M2.3 clock-sync behavior is intentionally preserved: it is
        // available while this Activity instance exists.
        clockSyncController.start();

        bindViews();
        loadDeviceAndSensorInfo();
        configureButtons();

        txtStatus.setText("READY");
        txtNetwork.setText("Network: IDLE");
        updateTimerText(0L);
        updateLastSessionUI();
        updateDeleteButtonState();
        requestNotificationPermissionIfNeeded();
    }

    private void bindViews() {
        txtStatus = findViewById(R.id.txtStatus);
        txtDevice = findViewById(R.id.txtDevice);
        txtAccel = findViewById(R.id.txtAccel);
        txtGyro = findViewById(R.id.txtGyro);
        txtNetwork = findViewById(R.id.txtNetwork);
        txtTimer = findViewById(R.id.txtTimer);
        txtCount = findViewById(R.id.txtCount);
        txtNetworkCount = findViewById(R.id.txtNetworkCount);
        txtFile = findViewById(R.id.txtFile);
        txtLastSession = findViewById(R.id.txtLastSession);

        editRecordName = findViewById(R.id.editRecordName);
        editPcIp = findViewById(R.id.editPcIp);
        editPcPort = findViewById(R.id.editPcPort);

        btnStart = findViewById(R.id.btnStart);
        btnStop = findViewById(R.id.btnStop);
        btnDeleteLast = findViewById(R.id.btnDeleteLast);
    }

    private void loadDeviceAndSensorInfo() {
        SensorManager sensorManager =
                (SensorManager) getSystemService(SENSOR_SERVICE);

        accelerometer = sensorManager.getDefaultSensor(
                Sensor.TYPE_ACCELEROMETER
        );
        gyroscope = sensorManager.getDefaultSensor(
                Sensor.TYPE_GYROSCOPE
        );

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

        if (accelerometer != null) {
            txtAccel.setText(
                    "Accelerometer: "
                            + accelerometer.getName()
                            + "\nVendor: "
                            + accelerometer.getVendor()
            );
        } else {
            txtAccel.setText("Accelerometer: NOT FOUND");
        }

        if (gyroscope != null) {
            txtGyro.setText(
                    "Gyroscope: "
                            + gyroscope.getName()
                            + "\nVendor: "
                            + gyroscope.getVendor()
            );
        } else {
            txtGyro.setText("Gyroscope: NOT FOUND");
        }
    }

    private void configureButtons() {
        btnStart.setOnClickListener(v -> startRecording());
        btnStop.setOnClickListener(v -> stopRecording());
        btnDeleteLast.setOnClickListener(
                v -> confirmDeleteLastSession()
        );
    }

    private void startRecording() {
        if (starting || recording || stopping) {
            return;
        }

        if (accelerometer == null || gyroscope == null) {
            txtStatus.setText(
                    "ERROR: Required sensors unavailable"
            );
            return;
        }

        String rawName = editRecordName
                .getText()
                .toString()
                .trim();

        if (rawName.isEmpty()) {
            editRecordName.setError(
                    "Recording name wajib diisi"
            );
            editRecordName.requestFocus();
            return;
        }

        String recordName = sanitizeRecordName(rawName);
        if (recordName.isEmpty()) {
            editRecordName.setError(
                    "Recording name tidak valid"
            );
            editRecordName.requestFocus();
            return;
        }

        String pcIp = editPcIp
                .getText()
                .toString()
                .trim();

        if (pcIp.isEmpty()) {
            editPcIp.setError("PC IP wajib diisi");
            editPcIp.requestFocus();
            return;
        }

        try {
            InetAddress.getByName(pcIp);
        } catch (Exception e) {
            editPcIp.setError("IP address tidak valid");
            editPcIp.requestFocus();
            return;
        }

        int pcPort;
        try {
            pcPort = Integer.parseInt(
                    editPcPort
                            .getText()
                            .toString()
                            .trim()
            );
        } catch (NumberFormatException e) {
            editPcPort.setError("Port tidak valid");
            editPcPort.requestFocus();
            return;
        }

        if (pcPort < 1 || pcPort > 65535) {
            editPcPort.setError("Port harus 1-65535");
            editPcPort.requestFocus();
            return;
        }

        Intent startIntent = new Intent(
                this,
                RecordingService.class
        );
        startIntent.setAction(RecordingService.ACTION_START);
        startIntent.putExtra(
                RecordingService.EXTRA_RECORD_NAME,
                recordName
        );
        startIntent.putExtra(
                RecordingService.EXTRA_PC_IP,
                pcIp
        );
        startIntent.putExtra(
                RecordingService.EXTRA_PC_PORT,
                pcPort
        );

        starting = true;
        recording = false;
        stopping = false;
        activeRecordName = recordName;

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(startIntent);
            } else {
                startService(startIntent);
            }
        } catch (Exception e) {
            starting = false;
            Log.e(TAG, "Cannot start RecordingService", e);
            txtStatus.setText(
                    "ERROR: Cannot start recording service"
            );
            return;
        }

        txtStatus.setText("STARTING\n" + recordName);
        txtNetwork.setText(
                "Network: STARTING\n"
                        + pcIp
                        + ":"
                        + pcPort
        );
        txtCount.setText("Total: 0\nACC: 0\nGYRO: 0");
        txtNetworkCount.setText(
                "UDP sent: 0\nQueue drops: 0\nSend errors: 0"
        );
        txtFile.setText("File: preparing...");
        updateTimerText(0L);
        setInputsEnabled(false);
        btnStart.setEnabled(false);
        btnStop.setEnabled(true);
        btnDeleteLast.setEnabled(false);
    }

    private void stopRecording() {
        if ((!starting && !recording) || stopping) {
            return;
        }

        stopping = true;
        starting = false;
        recording = false;

        txtStatus.setText(
                "STOPPING\n" + activeRecordName
        );
        txtNetwork.setText("Network: STOPPING");
        btnStart.setEnabled(false);
        btnStop.setEnabled(false);
        btnDeleteLast.setEnabled(false);

        if (recordingServiceBound && recordingService != null) {
            recordingService.requestStopFromUi();
            return;
        }

        Intent stopIntent = new Intent(
                this,
                RecordingService.class
        );
        stopIntent.setAction(RecordingService.ACTION_STOP);

        try {
            startService(stopIntent);
        } catch (Exception e) {
            Log.e(TAG, "Cannot stop RecordingService", e);
            stopping = false;
            txtStatus.setText(
                    "ERROR: Cannot stop recording service"
            );
            setInputsEnabled(true);
            btnStart.setEnabled(true);
            updateDeleteButtonState();
        }
    }

    private void bindRecordingService() {
        if (recordingServiceBindingActive) {
            return;
        }

        Intent serviceIntent = new Intent(
                this,
                RecordingService.class
        );

        recordingServiceBindingActive = bindService(
                serviceIntent,
                recordingServiceConnection,
                BIND_AUTO_CREATE
        );

        if (!recordingServiceBindingActive) {
            Log.w(TAG, "RecordingService bind request failed");
        }
    }

    private void unbindRecordingService() {
        if (!recordingServiceBindingActive) {
            return;
        }

        if (recordingServiceBound && recordingService != null) {
            recordingService.clearListener(recordingListener);
        }

        try {
            unbindService(recordingServiceConnection);
        } catch (IllegalArgumentException e) {
            Log.w(TAG, "RecordingService already unbound", e);
        }

        recordingServiceBindingActive = false;
        recordingServiceBound = false;
        recordingService = null;
    }

    private void renderRecordingSnapshot(
            RecordingService.RecordingSnapshot snapshot
    ) {
        if (snapshot == null) {
            return;
        }

        boolean wasActive = starting || recording || stopping;

        if (starting
                && "READY".equals(snapshot.status)
                && (snapshot.recordName == null
                || snapshot.recordName.isEmpty())) {
            return;
        }

        lastRecordingSnapshot = snapshot;
        starting = "STARTING".equals(snapshot.status);
        recording = snapshot.recording;
        stopping = snapshot.stopping;

        boolean active = starting || recording || stopping;

        if (snapshot.recordName != null
                && !snapshot.recordName.isEmpty()) {
            activeRecordName = snapshot.recordName;
        }

        String statusText = snapshot.status;
        if ((snapshot.recording
                || snapshot.stopping
                || "STOPPED".equals(snapshot.status))
                && snapshot.recordName != null
                && !snapshot.recordName.isEmpty()) {
            statusText =
                    snapshot.status
                            + "\n"
                            + snapshot.recordName;
        }
        txtStatus.setText(statusText);

        if (snapshot.pcIp != null
                && !snapshot.pcIp.isEmpty()
                && snapshot.pcPort > 0) {
            txtNetwork.setText(
                    "Network: "
                            + snapshot.networkStatus
                            + "\n"
                            + snapshot.pcIp
                            + ":"
                            + snapshot.pcPort
            );
        } else {
            txtNetwork.setText(
                    "Network: " + snapshot.networkStatus
            );
        }

        txtCount.setText(
                "Total: "
                        + snapshot.totalSamples
                        + "\nACC: "
                        + snapshot.accelSamples
                        + "\nGYRO: "
                        + snapshot.gyroSamples
        );

        txtNetworkCount.setText(
                "UDP sent: "
                        + snapshot.udpPacketsSent
                        + "\nQueue drops: "
                        + snapshot.networkQueueDrops
                        + "\nSend errors: "
                        + snapshot.networkSendErrors
        );

        if (snapshot.currentFilePath != null
                && !snapshot.currentFilePath.isEmpty()) {
            txtFile.setText(
                    "Local file:\n"
                            + snapshot.currentFilePath
            );
        }

        updateTimerText(snapshot.elapsedMs);
        setInputsEnabled(!active);
        btnStart.setEnabled(!active);
        btnStop.setEnabled(snapshot.recording || starting);

        if (active) {
            btnDeleteLast.setEnabled(false);
        } else {
            updateLastSessionUI();
            updateDeleteButtonState();
        }

        if (wasActive
                && !active
                && "STOPPED".equals(snapshot.status)) {
            editRecordName.setText("");
            Toast.makeText(
                    this,
                    "Session tersimpan: "
                            + snapshot.recordName,
                    Toast.LENGTH_SHORT
            ).show();
        }
    }

    private void setInputsEnabled(boolean enabled) {
        editRecordName.setEnabled(enabled);
        editPcIp.setEnabled(enabled);
        editPcPort.setEnabled(enabled);
    }

    private void updateTimerText(long elapsedMs) {
        if (txtTimer == null) {
            return;
        }

        txtTimer.setText(
                "Recording time: "
                        + RecordingTimeFormatter.formatElapsed(
                        elapsedMs
                )
        );
    }

    private void startTimerTicker() {
        timerTickerActive = true;
        if (uiTimerHandler != null) {
            uiTimerHandler.removeCallbacks(timerRunnable);
            uiTimerHandler.post(timerRunnable);
        }
    }

    private void stopTimerTicker() {
        timerTickerActive = false;
        if (uiTimerHandler != null) {
            uiTimerHandler.removeCallbacks(timerRunnable);
        }
    }

    private void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            return;
        }

        if (checkSelfPermission(
                Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED) {
            return;
        }

        requestPermissions(
                new String[]{Manifest.permission.POST_NOTIFICATIONS},
                NOTIFICATION_PERMISSION_REQUEST
        );
    }

    private String sanitizeRecordName(String input) {
        String cleaned = input
                .trim()
                .toLowerCase(Locale.US);
        cleaned = cleaned.replaceAll("\\s+", "_");
        cleaned = cleaned.replaceAll("[^a-z0-9_-]", "");
        cleaned = cleaned.replaceAll("_+", "_");
        return cleaned;
    }

    private File getSessionsDirectory() {
        File base = getExternalFilesDir(null);
        if (base == null) {
            base = getFilesDir();
        }
        return new File(base, "sessions");
    }

    private File findLatestImuFile() {
        File directory = getSessionsDirectory();
        if (!directory.exists()) {
            return null;
        }

        File[] files = directory.listFiles();
        if (files == null || files.length == 0) {
            return null;
        }

        File latestFile = null;
        for (File file : files) {
            String name = file.getName();
            if (!name.startsWith("imu_")
                    || !name.endsWith(".csv")) {
                continue;
            }

            if (latestFile == null
                    || file.lastModified()
                    > latestFile.lastModified()) {
                latestFile = file;
            }
        }
        return latestFile;
    }

    private File findMatchingMetadataFile(File imuFile) {
        if (imuFile == null) {
            return null;
        }

        String imuName = imuFile.getName();
        String suffix = imuName.substring(
                "imu_".length(),
                imuName.length() - ".csv".length()
        );

        return new File(
                getSessionsDirectory(),
                "meta_" + suffix + ".txt"
        );
    }

    private String readRecordNameFromMetadata(File metaFile) {
        if (metaFile == null || !metaFile.exists()) {
            return "unknown";
        }

        try (BufferedReader reader = new BufferedReader(
                new FileReader(metaFile)
        )) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.startsWith("record_name=")) {
                    return line.substring(
                            "record_name=".length()
                    );
                }
            }
        } catch (IOException e) {
            Log.e(TAG, "Cannot read metadata", e);
        }

        return "unknown";
    }

    private void updateDeleteButtonState() {
        if (btnDeleteLast == null) {
            return;
        }

        if (starting || recording || stopping) {
            btnDeleteLast.setEnabled(false);
            return;
        }

        btnDeleteLast.setEnabled(
                findLatestImuFile() != null
        );
    }

    private void updateLastSessionUI() {
        if (txtLastSession == null) {
            return;
        }

        File imuFile = findLatestImuFile();
        if (imuFile == null) {
            txtLastSession.setText("Last session: -");
            return;
        }

        File metaFile = findMatchingMetadataFile(imuFile);
        String lastName = readRecordNameFromMetadata(metaFile);

        txtLastSession.setText(
                "Last local session:\n"
                        + lastName
                        + "\n"
                        + imuFile.getName()
        );
    }

    private void confirmDeleteLastSession() {
        if (starting || recording || stopping) {
            txtStatus.setText(
                    "Cannot delete while recording"
            );
            return;
        }

        File imuFile = findLatestImuFile();
        if (imuFile == null) {
            txtStatus.setText(
                    "No local recording available"
            );
            updateDeleteButtonState();
            return;
        }

        File metaFile = findMatchingMetadataFile(imuFile);
        String lastName = readRecordNameFromMetadata(metaFile);

        new AlertDialog.Builder(this)
                .setTitle("Delete Last Local Recording?")
                .setMessage(
                        "Recording:\n"
                                + lastName
                                + "\n\nCSV:\n"
                                + imuFile.getName()
                                + "\n\nMetadata:\n"
                                + (metaFile != null
                                ? metaFile.getName()
                                : "-")
                                + "\n\n"
                                + "PC receiver log tidak ikut dihapus."
                )
                .setNegativeButton("CANCEL", null)
                .setPositiveButton(
                        "DELETE",
                        (dialog, which) -> deleteSession(
                                lastName,
                                imuFile,
                                metaFile
                        )
                )
                .show();
    }

    private void deleteSession(
            String deletedRecordName,
            File imuFile,
            File metaFile
    ) {
        writeDeletionAudit(
                deletedRecordName,
                imuFile,
                metaFile
        );

        boolean imuDeleted =
                imuFile == null
                        || !imuFile.exists()
                        || imuFile.delete();
        boolean metaDeleted =
                metaFile == null
                        || !metaFile.exists()
                        || metaFile.delete();

        if (imuDeleted && metaDeleted) {
            txtStatus.setText(
                    "DELETED\n" + deletedRecordName
            );
            txtFile.setText("File: -");
            txtCount.setText("Total: 0\nACC: 0\nGYRO: 0");
            txtNetworkCount.setText(
                    "UDP sent: 0\nQueue drops: 0\nSend errors: 0"
            );
            updateTimerText(0L);

            Toast.makeText(
                    this,
                    "Local recording deleted: "
                            + deletedRecordName,
                    Toast.LENGTH_SHORT
            ).show();
        } else {
            txtStatus.setText(
                    "ERROR deleting local files"
            );
        }

        updateLastSessionUI();
        updateDeleteButtonState();
    }

    private void writeDeletionAudit(
            String deletedRecordName,
            File imuFile,
            File metaFile
    ) {
        File directory = getSessionsDirectory();
        if (!directory.exists() && !directory.mkdirs()) {
            Log.e(TAG, "Cannot create session directory for audit");
            return;
        }

        File auditFile = new File(
                directory,
                "deletion_audit.csv"
        );
        boolean newFile = !auditFile.exists();

        try (BufferedWriter auditWriter = new BufferedWriter(
                new FileWriter(auditFile, true)
        )) {
            if (newFile) {
                auditWriter.write(
                        "deleted_at,record_name,imu_file,metadata_file\n"
                );
            }

            String deletedAt = new SimpleDateFormat(
                    "yyyy-MM-dd'T'HH:mm:ss.SSS",
                    Locale.US
            ).format(new Date());

            auditWriter.write(
                    deletedAt
                            + ","
                            + deletedRecordName
                            + ","
                            + (imuFile != null
                            ? imuFile.getName()
                            : "")
                            + ","
                            + (metaFile != null
                            ? metaFile.getName()
                            : "")
                            + "\n"
            );
            auditWriter.flush();
        } catch (IOException e) {
            Log.e(TAG, "Cannot write deletion audit", e);
        }
    }

    @Override
    protected void onStart() {
        super.onStart();
        bindRecordingService();
        startTimerTicker();
    }

    @Override
    protected void onStop() {
        stopTimerTicker();
        unbindRecordingService();

        // Intentionally no recording stop here. A user may leave the app
        // during a research trial and the foreground service must continue.
        super.onStop();
    }

    @Override
    protected void onPause() {
        // Intentionally no stopRecording(). This was the original bug:
        // onPause used to end the session whenever the UI lost focus.
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        clockSyncController.stop();
        stopTimerTicker();
        unbindRecordingService();

        // RecordingService is a started foreground service and therefore has
        // an independent lifecycle. Destroying the Activity must not stop it.
        super.onDestroy();
    }
}
