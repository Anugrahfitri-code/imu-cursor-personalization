package com.imucursor.research;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.os.Binder;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.util.Log;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * Owns the complete IMU acquisition lifecycle.
 *
 * The service is both started and bindable:
 * - started foreground service => recording survives Activity backgrounding / task removal;
 * - local binder => MainActivity can render current counters and elapsed time when visible.
 *
 * Normal recording stops only after an explicit ACTION_STOP/requestStopFromUi().
 */
public class RecordingService extends Service implements SensorEventListener {

    private static final String TAG = "IMU_RECORDING_SERVICE";

    public static final String ACTION_START =
            "com.imucursor.research.action.START_RECORDING";
    public static final String ACTION_STOP =
            "com.imucursor.research.action.STOP_RECORDING";

    public static final String EXTRA_RECORD_NAME = "record_name";
    public static final String EXTRA_PC_IP = "pc_ip";
    public static final String EXTRA_PC_PORT = "pc_port";

    private static final int SAMPLING_PERIOD_US = 10000;
    private static final int UDP_PROTOCOL_VERSION = 1;
    private static final int NETWORK_QUEUE_CAPACITY = 10000;

    private static final String NOTIFICATION_CHANNEL_ID =
            "imu_recording_channel";
    private static final int NOTIFICATION_ID = 2101;

    private final IBinder binder = new LocalBinder();
    private final Object stopLock = new Object();

    private Handler mainHandler;

    private SensorManager sensorManager;
    private Sensor accelerometer;
    private Sensor gyroscope;
    private HandlerThread sensorThread;
    private Handler sensorHandler;

    private final LinkedBlockingQueue<String> writeQueue =
            new LinkedBlockingQueue<>();
    private Thread writerThread;
    private volatile boolean writerRunning = false;
    private BufferedWriter writer;

    private final LinkedBlockingQueue<NetworkSample> networkQueue =
            new LinkedBlockingQueue<>(NETWORK_QUEUE_CAPACITY);
    private Thread networkThread;
    private volatile boolean networkRunning = false;
    private volatile boolean networkReady = false;
    private DatagramSocket udpSocket;
    private InetAddress pcAddress;

    private volatile boolean recording = false;
    private volatile boolean stopping = false;

    private volatile long globalSeq = 0;
    private volatile long accelSeq = 0;
    private volatile long gyroSeq = 0;
    private volatile long networkPacketsSent = 0;
    private volatile long networkQueueDrops = 0;
    private volatile long networkSendErrors = 0;

    private volatile long recordingStartElapsedNs = 0;
    private volatile long recordingStartElapsedMs = 0;
    private volatile long recordingStopElapsedNs = 0;
    private volatile long recordingStopElapsedMs = 0;

    private volatile String status = "READY";
    private volatile String networkStatus = "IDLE";
    private volatile String sessionId = "";
    private volatile String recordName = "";
    private volatile String pcIpString = "";
    private volatile int pcPort = 0;
    private volatile String currentFilePath = "";

    private File currentFile;
    private File metadataFile;

    private PowerManager.WakeLock wakeLock;

    private volatile Listener listener;

    public interface Listener {
        void onRecordingSnapshot(RecordingSnapshot snapshot);
    }

    public final class LocalBinder extends Binder {
        public RecordingService getService() {
            return RecordingService.this;
        }
    }

    public static final class RecordingSnapshot {
        public final boolean recording;
        public final boolean stopping;
        public final String status;
        public final String networkStatus;
        public final String sessionId;
        public final String recordName;
        public final String pcIp;
        public final int pcPort;
        public final String currentFilePath;
        public final long startElapsedRealtimeMs;
        public final long elapsedMs;
        public final long totalSamples;
        public final long accelSamples;
        public final long gyroSamples;
        public final long udpPacketsSent;
        public final long networkQueueDrops;
        public final long networkSendErrors;

        RecordingSnapshot(
                boolean recording,
                boolean stopping,
                String status,
                String networkStatus,
                String sessionId,
                String recordName,
                String pcIp,
                int pcPort,
                String currentFilePath,
                long startElapsedRealtimeMs,
                long elapsedMs,
                long totalSamples,
                long accelSamples,
                long gyroSamples,
                long udpPacketsSent,
                long networkQueueDrops,
                long networkSendErrors
        ) {
            this.recording = recording;
            this.stopping = stopping;
            this.status = status;
            this.networkStatus = networkStatus;
            this.sessionId = sessionId;
            this.recordName = recordName;
            this.pcIp = pcIp;
            this.pcPort = pcPort;
            this.currentFilePath = currentFilePath;
            this.startElapsedRealtimeMs = startElapsedRealtimeMs;
            this.elapsedMs = elapsedMs;
            this.totalSamples = totalSamples;
            this.accelSamples = accelSamples;
            this.gyroSamples = gyroSamples;
            this.udpPacketsSent = udpPacketsSent;
            this.networkQueueDrops = networkQueueDrops;
            this.networkSendErrors = networkSendErrors;
        }
    }

    private static final class NetworkSample {
        final String sessionId;
        final String recordName;
        final long seqGlobal;
        final long seqSensor;
        final String sensorType;
        final long sensorTimestampNs;
        final long callbackElapsedNs;
        final float x;
        final float y;
        final float z;
        final int accuracy;

        NetworkSample(
                String sessionId,
                String recordName,
                long seqGlobal,
                long seqSensor,
                String sensorType,
                long sensorTimestampNs,
                long callbackElapsedNs,
                float x,
                float y,
                float z,
                int accuracy
        ) {
            this.sessionId = sessionId;
            this.recordName = recordName;
            this.seqGlobal = seqGlobal;
            this.seqSensor = seqSensor;
            this.sensorType = sensorType;
            this.sensorTimestampNs = sensorTimestampNs;
            this.callbackElapsedNs = callbackElapsedNs;
            this.x = x;
            this.y = y;
            this.z = z;
            this.accuracy = accuracy;
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();

        mainHandler = new Handler(Looper.getMainLooper());

        sensorManager =
                (SensorManager) getSystemService(SENSOR_SERVICE);
        accelerometer = sensorManager.getDefaultSensor(
                Sensor.TYPE_ACCELEROMETER
        );
        gyroscope = sensorManager.getDefaultSensor(
                Sensor.TYPE_GYROSCOPE
        );

        sensorThread = new HandlerThread("IMUSensorThread");
        sensorThread.start();
        sensorHandler = new Handler(sensorThread.getLooper());

        createNotificationChannel();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return binder;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent != null ? intent.getAction() : null;

        if (ACTION_START.equals(action)) {
            if (recording || stopping) {
                notifyState();
                return START_NOT_STICKY;
            }

            // startForegroundService() must be promoted promptly.
            startForegroundCompat(
                    buildNotification("Menyiapkan recording IMU", false)
            );
            startRecording(intent);

        } else if (ACTION_STOP.equals(action)) {
            if (recording || stopping) {
                requestStop("user_stop");
            } else {
                // If an idle bound service receives ACTION_STOP via startService(),
                // do not accidentally leave it in the started state.
                stopSelf(startId);
            }
        }

        // A research recording must never be silently reconstructed after
        // process death because that would splice two acquisition epochs.
        // Foreground service + wake lock handles normal backgrounding; a
        // process/OS kill is treated as a technical interruption instead.
        return START_NOT_STICKY;
    }

    public void setListener(Listener listener) {
        this.listener = listener;
        notifyState();
    }

    public void clearListener(Listener listener) {
        if (this.listener == listener) {
            this.listener = null;
        }
    }

    public RecordingSnapshot getSnapshot() {
        long elapsedMs = 0L;

        if (recordingStartElapsedMs > 0L) {
            long endMs;

            if (recording) {
                endMs = SystemClock.elapsedRealtime();
            } else if (recordingStopElapsedMs > 0L) {
                endMs = recordingStopElapsedMs;
            } else {
                endMs = recordingStartElapsedMs;
            }

            elapsedMs = Math.max(
                    0L,
                    endMs - recordingStartElapsedMs
            );
        }

        return new RecordingSnapshot(
                recording,
                stopping,
                status,
                networkStatus,
                sessionId,
                recordName,
                pcIpString,
                pcPort,
                currentFilePath,
                recordingStartElapsedMs,
                elapsedMs,
                globalSeq,
                accelSeq,
                gyroSeq,
                networkPacketsSent,
                networkQueueDrops,
                networkSendErrors
        );
    }

    public void requestStopFromUi() {
        requestStop("user_stop");
    }

    private void startRecording(Intent intent) {
        status = "STARTING";
        networkStatus = "STARTING";
        notifyState();

        try {
            if (accelerometer == null || gyroscope == null) {
                failStart("Required sensors unavailable", null);
                return;
            }

            String requestedName = intent.getStringExtra(EXTRA_RECORD_NAME);
            String requestedIp = intent.getStringExtra(EXTRA_PC_IP);
            int requestedPort = intent.getIntExtra(EXTRA_PC_PORT, -1);

            recordName = sanitizeRecordName(requestedName);
            pcIpString = requestedIp != null ? requestedIp.trim() : "";
            pcPort = requestedPort;

            if (recordName.isEmpty()) {
                failStart("Recording name tidak valid", null);
                return;
            }

            if (pcIpString.isEmpty()) {
                failStart("PC IP tidak valid", null);
                return;
            }

            if (pcPort < 1 || pcPort > 65535) {
                failStart("UDP port tidak valid", null);
                return;
            }

            pcAddress = InetAddress.getByName(pcIpString);

            // Clear the previous session snapshot only after the new request
            // has passed its basic validation. This prevents stale file paths,
            // counters, or timer epochs from being shown if a new start fails.
            sessionId = "";
            currentFile = null;
            metadataFile = null;
            currentFilePath = "";
            recordingStartElapsedNs = 0L;
            recordingStartElapsedMs = 0L;
            recordingStopElapsedNs = 0L;
            recordingStopElapsedMs = 0L;
            resetSessionCounters();

            sessionId = new SimpleDateFormat(
                    "yyyyMMdd_HHmmss_SSS",
                    Locale.US
            ).format(new Date());

            File directory = getSessionsDirectory();
            if (!directory.exists() && !directory.mkdirs()) {
                failStart("Tidak dapat membuat direktori session", null);
                return;
            }

            String suffix = recordName + "_" + sessionId;
            currentFile = new File(
                    directory,
                    "imu_" + suffix + ".csv"
            );
            metadataFile = new File(
                    directory,
                    "meta_" + suffix + ".txt"
            );
            currentFilePath = currentFile.getAbsolutePath();

            writer = new BufferedWriter(
                    new FileWriter(currentFile)
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

            recordingStartElapsedNs =
                    SystemClock.elapsedRealtimeNanos();
            recordingStartElapsedMs =
                    recordingStartElapsedNs / 1_000_000L;
            recordingStopElapsedNs = 0L;
            recordingStopElapsedMs = 0L;

            writeSessionMetadata();

            writerRunning = true;
            writerThread = new Thread(
                    this::writerLoop,
                    "IMUWriterThread"
            );
            writerThread.start();

            networkRunning = true;
            networkReady = false;
            networkThread = new Thread(
                    this::networkLoop,
                    "IMUNetworkThread"
            );
            networkThread.start();

            recording = true;
            stopping = false;

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

            if (!accelRegistered || !gyroRegistered) {
                Log.e(
                        TAG,
                        "Sensor registration failed. ACC="
                                + accelRegistered
                                + " GYRO="
                                + gyroRegistered
                );
                status = "ERROR: Sensor registration failed";
                requestStop("sensor_registration_failed");
                return;
            }

            acquireWakeLock();

            status = "RECORDING";
            updateForegroundNotification();
            notifyState();

            Log.i(
                    TAG,
                    "Session started name="
                            + recordName
                            + " session="
                            + sessionId
                            + " target="
                            + pcIpString
                            + ":"
                            + pcPort
            );

        } catch (Exception e) {
            if (recording) {
                Log.e(TAG, "Recording start failed after acquisition setup", e);
                status = "ERROR: Gagal memulai recording";
                requestStop("start_exception");
            } else {
                failStart("Gagal memulai recording", e);
            }
        }
    }

    private void resetSessionCounters() {
        globalSeq = 0L;
        accelSeq = 0L;
        gyroSeq = 0L;
        networkPacketsSent = 0L;
        networkQueueDrops = 0L;
        networkSendErrors = 0L;
        writeQueue.clear();
        networkQueue.clear();
    }

    private void failStart(String message, Exception error) {
        if (error != null) {
            Log.e(TAG, message, error);
        } else {
            Log.e(TAG, message);
        }

        status = "ERROR: " + message;
        networkStatus = "IDLE";
        recording = false;
        stopping = false;

        sensorManager.unregisterListener(this);
        writerRunning = false;
        networkRunning = false;

        if (udpSocket != null) {
            udpSocket.close();
            udpSocket = null;
        }

        closeWriterQuietly();
        releaseWakeLock();
        notifyState();
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    @Override
    public void onSensorChanged(SensorEvent event) {
        if (!recording) {
            return;
        }

        long callbackElapsedNs =
                SystemClock.elapsedRealtimeNanos();
        long sensorTimestampNs = event.timestamp;

        String sensorType;
        long sensorSeq;

        if (event.sensor.getType() == Sensor.TYPE_ACCELEROMETER) {
            accelSeq++;
            sensorSeq = accelSeq;
            sensorType = "ACC";
        } else if (event.sensor.getType() == Sensor.TYPE_GYROSCOPE) {
            gyroSeq++;
            sensorSeq = gyroSeq;
            sensorType = "GYRO";
        } else {
            return;
        }

        globalSeq++;

        float x = event.values[0];
        float y = event.values[1];
        float z = event.values[2];

        String localRow =
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

        writeQueue.offer(localRow);

        NetworkSample networkSample = new NetworkSample(
                sessionId,
                recordName,
                globalSeq,
                sensorSeq,
                sensorType,
                sensorTimestampNs,
                callbackElapsedNs,
                x,
                y,
                z,
                event.accuracy
        );

        if (!networkQueue.offer(networkSample)) {
            networkQueueDrops++;
        }

        if (globalSeq % 200L == 0L) {
            notifyState();
        }
    }

    private void writerLoop() {
        long writtenRows = 0L;

        try {
            while (writerRunning || !writeQueue.isEmpty()) {
                String row = writeQueue.poll(
                        100L,
                        TimeUnit.MILLISECONDS
                );

                if (row == null) {
                    continue;
                }

                writer.write(row);
                writtenRows++;

                if (writtenRows % 1000L == 0L) {
                    writer.flush();
                    Log.i(
                            TAG,
                            "LOCAL written="
                                    + writtenRows
                                    + " queue="
                                    + writeQueue.size()
                    );
                }
            }

            if (writer != null) {
                writer.flush();
            }

        } catch (IOException e) {
            Log.e(TAG, "Local writer I/O error", e);
            status = "ERROR: Local writer I/O";
            notifyState();

            if (recording && !stopping) {
                requestStop("local_writer_error");
            }

        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            Log.e(TAG, "Local writer interrupted", e);
        }
    }

    private void networkLoop() {
        try {
            udpSocket = new DatagramSocket();
            udpSocket.connect(pcAddress, pcPort);

            networkReady = true;
            networkStatus = "STREAMING";
            notifyState();

            Log.i(
                    TAG,
                    "UDP socket ready -> "
                            + pcIpString
                            + ":"
                            + pcPort
            );

            while (networkRunning || !networkQueue.isEmpty()) {
                NetworkSample sample = networkQueue.poll(
                        100L,
                        TimeUnit.MILLISECONDS
                );

                if (sample == null) {
                    continue;
                }

                long sendElapsedNs =
                        SystemClock.elapsedRealtimeNanos();

                String message =
                        "DATA,"
                                + UDP_PROTOCOL_VERSION
                                + ","
                                + sample.sessionId
                                + ","
                                + sample.recordName
                                + ","
                                + sample.seqGlobal
                                + ","
                                + sample.seqSensor
                                + ","
                                + sample.sensorType
                                + ","
                                + sample.sensorTimestampNs
                                + ","
                                + sample.callbackElapsedNs
                                + ","
                                + sendElapsedNs
                                + ","
                                + sample.x
                                + ","
                                + sample.y
                                + ","
                                + sample.z
                                + ","
                                + sample.accuracy;

                byte[] payload = message.getBytes(
                        StandardCharsets.UTF_8
                );
                DatagramPacket packet = new DatagramPacket(
                        payload,
                        payload.length
                );

                try {
                    udpSocket.send(packet);
                    networkPacketsSent++;
                } catch (IOException e) {
                    networkSendErrors++;
                    Log.e(TAG, "UDP send error", e);
                }
            }

        } catch (Exception e) {
            networkReady = false;
            networkSendErrors++;
            networkStatus = "ERROR";
            Log.e(TAG, "UDP network initialization error", e);
            notifyState();

        } finally {
            networkReady = false;

            if (udpSocket != null) {
                udpSocket.close();
                udpSocket = null;
            }

            if (stopping) {
                networkStatus = "STOPPING";
            } else if (!recording) {
                networkStatus = "STOPPED";
            }

            notifyState();

            Log.i(
                    TAG,
                    "UDP thread stopped sent="
                            + networkPacketsSent
                            + " queueDrops="
                            + networkQueueDrops
                            + " sendErrors="
                            + networkSendErrors
            );
        }
    }

    private void requestStop(String reason) {
        synchronized (stopLock) {
            if (!recording || stopping) {
                return;
            }

            stopping = true;
            recording = false;
            recordingStopElapsedNs =
                    SystemClock.elapsedRealtimeNanos();
            recordingStopElapsedMs =
                    recordingStopElapsedNs / 1_000_000L;
            status = "STOPPING";
            networkStatus = "STOPPING";

            // Stop the source first. No new samples are accepted after this point.
            sensorManager.unregisterListener(this);

            updateForegroundNotification();
            notifyState();

            Thread stopThread = new Thread(
                    () -> finishStop(reason),
                    "IMUStopThread"
            );
            stopThread.start();
        }
    }

    private void finishStop(String reason) {
        writerRunning = false;
        joinWorker(writerThread, "writer");

        networkRunning = false;
        joinWorker(networkThread, "network");

        closeWriterQuietly();
        appendFinalMetadata(reason);
        releaseWakeLock();

        status = "STOPPED";
        networkStatus = "STOPPED";
        stopping = false;

        notifyState();

        Log.i(
                TAG,
                "Session stopped name="
                        + recordName
                        + " total="
                        + globalSeq
                        + " ACC="
                        + accelSeq
                        + " GYRO="
                        + gyroSeq
                        + " localQueue="
                        + writeQueue.size()
                        + " UDPsent="
                        + networkPacketsSent
                        + " networkQueue="
                        + networkQueue.size()
                        + " networkQueueDrops="
                        + networkQueueDrops
                        + " sendErrors="
                        + networkSendErrors
                        + " reason="
                        + reason
        );

        mainHandler.post(() -> {
            stopForeground(STOP_FOREGROUND_REMOVE);
            stopSelf();
        });
    }

    private void joinWorker(Thread worker, String name) {
        if (worker == null || worker == Thread.currentThread()) {
            return;
        }

        try {
            worker.join(5000L);

            if (worker.isAlive()) {
                Log.w(TAG, name + " thread did not drain in 5 s; interrupting");

                if ("network".equals(name) && udpSocket != null) {
                    udpSocket.close();
                }

                worker.interrupt();
                worker.join(1000L);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            Log.w(TAG, "Interrupted while joining " + name, e);
        }
    }

    private void closeWriterQuietly() {
        if (writer == null) {
            return;
        }

        try {
            writer.flush();
            writer.close();
        } catch (IOException e) {
            Log.e(TAG, "Error closing local CSV", e);
        } finally {
            writer = null;
        }
    }

    private void writeSessionMetadata() {
        if (metadataFile == null) {
            return;
        }

        try (BufferedWriter metadataWriter =
                     new BufferedWriter(new FileWriter(metadataFile))) {

            metadataWriter.write("session_id=" + sessionId + "\n");
            metadataWriter.write("record_name=" + recordName + "\n");
            metadataWriter.write("manufacturer=" + Build.MANUFACTURER + "\n");
            metadataWriter.write("model=" + Build.MODEL + "\n");
            metadataWriter.write("android_version=" + Build.VERSION.RELEASE + "\n");
            metadataWriter.write("api_level=" + Build.VERSION.SDK_INT + "\n");
            metadataWriter.write("requested_sampling_us=" + SAMPLING_PERIOD_US + "\n");
            metadataWriter.write(
                    "requested_sampling_hz="
                            + (1_000_000.0 / SAMPLING_PERIOD_US)
                            + "\n"
            );
            metadataWriter.write(
                    "session_start_elapsed_ns="
                            + recordingStartElapsedNs
                            + "\n"
            );
            metadataWriter.write("udp_protocol_version=" + UDP_PROTOCOL_VERSION + "\n");
            metadataWriter.write("udp_target_ip=" + pcIpString + "\n");
            metadataWriter.write("udp_target_port=" + pcPort + "\n");
            metadataWriter.write("recording_owner=foreground_service\n");
            metadataWriter.write("activity_background_stop=false\n");

            if (accelerometer != null) {
                metadataWriter.write("accelerometer_name=" + accelerometer.getName() + "\n");
                metadataWriter.write("accelerometer_vendor=" + accelerometer.getVendor() + "\n");
                metadataWriter.write("accelerometer_version=" + accelerometer.getVersion() + "\n");
                metadataWriter.write("accelerometer_resolution=" + accelerometer.getResolution() + "\n");
                metadataWriter.write("accelerometer_max_range=" + accelerometer.getMaximumRange() + "\n");
                metadataWriter.write("accelerometer_min_delay_us=" + accelerometer.getMinDelay() + "\n");
            }

            if (gyroscope != null) {
                metadataWriter.write("gyroscope_name=" + gyroscope.getName() + "\n");
                metadataWriter.write("gyroscope_vendor=" + gyroscope.getVendor() + "\n");
                metadataWriter.write("gyroscope_version=" + gyroscope.getVersion() + "\n");
                metadataWriter.write("gyroscope_resolution=" + gyroscope.getResolution() + "\n");
                metadataWriter.write("gyroscope_max_range=" + gyroscope.getMaximumRange() + "\n");
                metadataWriter.write("gyroscope_min_delay_us=" + gyroscope.getMinDelay() + "\n");
            }

        } catch (IOException e) {
            Log.e(TAG, "Cannot write metadata", e);
        }
    }

    private void appendFinalMetadata(String stopReason) {
        if (metadataFile == null) {
            return;
        }

        long durationMs = 0L;
        if (recordingStartElapsedMs > 0L && recordingStopElapsedMs > 0L) {
            durationMs = Math.max(
                    0L,
                    recordingStopElapsedMs - recordingStartElapsedMs
            );
        }

        try (BufferedWriter metadataWriter =
                     new BufferedWriter(new FileWriter(metadataFile, true))) {

            long durationNs = 0L;
            if (recordingStartElapsedNs > 0L
                    && recordingStopElapsedNs > 0L) {
                durationNs = Math.max(
                        0L,
                        recordingStopElapsedNs - recordingStartElapsedNs
                );
            }

            metadataWriter.write("session_stop_reason=" + stopReason + "\n");
            metadataWriter.write("session_stop_elapsed_ns=" + recordingStopElapsedNs + "\n");
            metadataWriter.write("session_duration_ns=" + durationNs + "\n");
            metadataWriter.write("session_duration_ms=" + durationMs + "\n");
            metadataWriter.write("final_total_samples=" + globalSeq + "\n");
            metadataWriter.write("final_acc_samples=" + accelSeq + "\n");
            metadataWriter.write("final_gyro_samples=" + gyroSeq + "\n");
            metadataWriter.write("final_udp_packets_sent=" + networkPacketsSent + "\n");
            metadataWriter.write("final_network_queue_drops=" + networkQueueDrops + "\n");
            metadataWriter.write("final_udp_send_errors=" + networkSendErrors + "\n");
            metadataWriter.write("final_local_queue_remaining=" + writeQueue.size() + "\n");
            metadataWriter.write("final_network_queue_remaining=" + networkQueue.size() + "\n");

        } catch (IOException e) {
            Log.e(TAG, "Cannot append final metadata", e);
        }
    }

    private String sanitizeRecordName(String input) {
        if (input == null) {
            return "";
        }

        String cleaned = input.trim().toLowerCase(Locale.US);
        cleaned = cleaned.replaceAll("\\s+", "_");
        cleaned = cleaned.replaceAll("[^a-z0-9_-]", "");
        cleaned = cleaned.replaceAll("_+", "_");
        return cleaned;
    }

    private File getSessionsDirectory() {
        File base = getExternalFilesDir(null);
        if (base == null) {
            return new File(getFilesDir(), "sessions");
        }
        return new File(base, "sessions");
    }

    private void acquireWakeLock() {
        if (wakeLock != null && wakeLock.isHeld()) {
            return;
        }

        PowerManager powerManager =
                (PowerManager) getSystemService(POWER_SERVICE);

        wakeLock = powerManager.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                "IMUResearchClient:RecordingWakeLock"
        );
        wakeLock.setReferenceCounted(false);
        wakeLock.acquire();
    }

    private void releaseWakeLock() {
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
        }
        wakeLock = null;
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }

        NotificationChannel channel = new NotificationChannel(
                NOTIFICATION_CHANNEL_ID,
                "IMU Recording",
                NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription(
                "Menjaga recording IMU tetap aktif saat aplikasi berada di background"
        );

        NotificationManager notificationManager =
                getSystemService(NotificationManager.class);
        notificationManager.createNotificationChannel(channel);
    }

    private Notification buildNotification(
            String contentText,
            boolean showChronometer
    ) {
        Intent openIntent = new Intent(this, MainActivity.class);
        openIntent.setFlags(
                Intent.FLAG_ACTIVITY_SINGLE_TOP
                        | Intent.FLAG_ACTIVITY_CLEAR_TOP
        );

        int pendingFlags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            pendingFlags |= PendingIntent.FLAG_IMMUTABLE;
        }

        PendingIntent contentIntent = PendingIntent.getActivity(
                this,
                0,
                openIntent,
                pendingFlags
        );

        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(
                    this,
                    NOTIFICATION_CHANNEL_ID
            );
        } else {
            builder = new Notification.Builder(this);
        }

        builder.setSmallIcon(R.drawable.ic_launcher_foreground)
                .setContentTitle("IMU recording aktif")
                .setContentText(contentText)
                .setContentIntent(contentIntent)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setCategory(Notification.CATEGORY_SERVICE);

        if (showChronometer && recordingStartElapsedMs > 0L) {
            long startWallClockMs =
                    System.currentTimeMillis()
                            - (
                            SystemClock.elapsedRealtime()
                                    - recordingStartElapsedMs
                    );

            builder.setWhen(startWallClockMs)
                    .setUsesChronometer(true)
                    .setShowWhen(true);
        } else {
            builder.setShowWhen(false);
        }

        return builder.build();
    }

    private void startForegroundCompat(Notification notification) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                    NOTIFICATION_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            );
        } else {
            startForeground(
                    NOTIFICATION_ID,
                    notification
            );
        }
    }

    private void updateForegroundNotification() {
        NotificationManager notificationManager =
                (NotificationManager) getSystemService(NOTIFICATION_SERVICE);

        String text;
        boolean showChronometer;

        if (stopping) {
            text = "Menyelesaikan dan menyimpan " + recordName;
            showChronometer = false;
        } else if (recording) {
            text = recordName + " • ketuk untuk kembali ke aplikasi";
            showChronometer = true;
        } else {
            text = "Menyiapkan recording IMU";
            showChronometer = false;
        }

        notificationManager.notify(
                NOTIFICATION_ID,
                buildNotification(text, showChronometer)
        );
    }

    private void notifyState() {
        if (mainHandler == null) {
            return;
        }

        mainHandler.post(() -> {
            Listener currentListener = listener;
            if (currentListener != null) {
                currentListener.onRecordingSnapshot(
                        getSnapshot()
                );
            }
        });
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        // Intentionally do not stop. android:stopWithTask="false" and the
        // foreground service keep acquisition active after the UI task is
        // removed. The user returns to the app to press STOP.
        Log.i(TAG, "UI task removed while recording=" + recording);
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onAccuracyChanged(Sensor sensor, int accuracy) {
        Log.i(
                TAG,
                "Accuracy: "
                        + sensor.getName()
                        + " = "
                        + accuracy
        );
    }

    @Override
    public void onDestroy() {
        listener = null;

        if (recording || stopping) {
            // Best-effort emergency closure. This is not a normal user stop.
            recording = false;
            stopping = false;
            recordingStopElapsedNs = SystemClock.elapsedRealtimeNanos();
            recordingStopElapsedMs = recordingStopElapsedNs / 1_000_000L;
            sensorManager.unregisterListener(this);
            writerRunning = false;
            networkRunning = false;

            if (udpSocket != null) {
                udpSocket.close();
                udpSocket = null;
            }

            closeWriterQuietly();
            appendFinalMetadata("service_destroyed");
            releaseWakeLock();
        }

        if (sensorThread != null) {
            sensorThread.quitSafely();
            sensorThread = null;
        }

        super.onDestroy();
    }
}
