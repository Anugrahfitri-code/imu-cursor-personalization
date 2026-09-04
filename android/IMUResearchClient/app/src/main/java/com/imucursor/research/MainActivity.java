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

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;

import java.nio.charset.StandardCharsets;

import java.text.SimpleDateFormat;

import java.util.Date;
import java.util.Locale;

import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;


public class MainActivity extends AppCompatActivity
        implements SensorEventListener {

    // =========================================================
    // GENERAL
    // =========================================================

    private static final String TAG = "IMU_RESEARCH";

    /*
     * Nominal sampling request:
     * 10 ms = 100 Hz.
     */
    private static final int SAMPLING_PERIOD_US = 10000;

    /*
     * Versioned UDP protocol.
     *
     * DATA,1,...
     *
     * Prefix DATA memungkinkan kita menambahkan
     * SYNC packets pada M2.3 tanpa merusak format DATA.
     */
    private static final int UDP_PROTOCOL_VERSION = 1;

    /*
     * Capacity besar tetapi bounded.
     *
     * Kalau network tidak mampu mengikuti acquisition,
     * kita mencatat local queue drop secara eksplisit
     * daripada membiarkan memory bertambah tanpa batas.
     */
    private static final int NETWORK_QUEUE_CAPACITY = 10000;


    // =========================================================
    // SENSOR
    // =========================================================

    private SensorManager sensorManager;

    private Sensor accelerometer;
    private Sensor gyroscope;


    // =========================================================
    // SENSOR THREAD
    // =========================================================

    private HandlerThread sensorThread;
    private Handler sensorHandler;


    // =========================================================
    // LOCAL WRITER
    // =========================================================

    private final LinkedBlockingQueue<String> writeQueue =
            new LinkedBlockingQueue<>();

    private Thread writerThread;

    private volatile boolean writerRunning = false;

    private BufferedWriter writer;


    // =========================================================
    // NETWORK
    // =========================================================

    private final LinkedBlockingQueue<NetworkSample> networkQueue =
            new LinkedBlockingQueue<>(
                    NETWORK_QUEUE_CAPACITY
            );

    private Thread networkThread;

    private volatile boolean networkRunning = false;
    private volatile boolean networkReady = false;

    private DatagramSocket udpSocket;

    private InetAddress pcAddress;
    private int pcPort;

    private String pcIpString;

    private long networkPacketsSent = 0;
    private long networkQueueDrops = 0;
    private long networkSendErrors = 0;


    // =========================================================
    // RECORDING
    // =========================================================

    private volatile boolean recording = false;

    private long globalSeq = 0;
    private long accelSeq = 0;
    private long gyroSeq = 0;

    private String sessionId;
    private String recordName;

    private File currentFile;
    private File metadataFile;


    // =========================================================
    // UI
    // =========================================================

    private TextView txtStatus;
    private TextView txtDevice;
    private TextView txtAccel;
    private TextView txtGyro;

    private TextView txtNetwork;

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


    // =========================================================
    // NETWORK SAMPLE
    // =========================================================

    private static class NetworkSample {

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


    // =========================================================
    // ON CREATE
    // =========================================================

    @Override
    protected void onCreate(Bundle savedInstanceState) {

        super.onCreate(savedInstanceState);

        setContentView(
                R.layout.activity_main
        );


        // -----------------------------------------------------
        // UI bindings
        // -----------------------------------------------------

        txtStatus =
                findViewById(
                        R.id.txtStatus
                );

        txtDevice =
                findViewById(
                        R.id.txtDevice
                );

        txtAccel =
                findViewById(
                        R.id.txtAccel
                );

        txtGyro =
                findViewById(
                        R.id.txtGyro
                );

        txtNetwork =
                findViewById(
                        R.id.txtNetwork
                );

        txtCount =
                findViewById(
                        R.id.txtCount
                );

        txtNetworkCount =
                findViewById(
                        R.id.txtNetworkCount
                );

        txtFile =
                findViewById(
                        R.id.txtFile
                );

        txtLastSession =
                findViewById(
                        R.id.txtLastSession
                );

        editRecordName =
                findViewById(
                        R.id.editRecordName
                );

        editPcIp =
                findViewById(
                        R.id.editPcIp
                );

        editPcPort =
                findViewById(
                        R.id.editPcPort
                );

        btnStart =
                findViewById(
                        R.id.btnStart
                );

        btnStop =
                findViewById(
                        R.id.btnStop
                );

        btnDeleteLast =
                findViewById(
                        R.id.btnDeleteLast
                );


        // -----------------------------------------------------
        // Sensors
        // -----------------------------------------------------

        sensorManager =
                (SensorManager)
                        getSystemService(
                                SENSOR_SERVICE
                        );


        accelerometer =
                sensorManager.getDefaultSensor(
                        Sensor.TYPE_ACCELEROMETER
                );


        gyroscope =
                sensorManager.getDefaultSensor(
                        Sensor.TYPE_GYROSCOPE
                );


        // -----------------------------------------------------
        // Device UI
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
        // Dedicated sensor thread
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


        txtStatus.setText(
                "READY"
        );

        txtNetwork.setText(
                "Network: IDLE"
        );

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
        // Validate sensors
        // -----------------------------------------------------

        if (accelerometer == null
                || gyroscope == null) {

            txtStatus.setText(
                    "ERROR: Required sensors unavailable"
            );

            return;
        }


        // -----------------------------------------------------
        // Validate record name
        // -----------------------------------------------------

        String inputRecordName =
                editRecordName
                        .getText()
                        .toString()
                        .trim();


        if (inputRecordName.isEmpty()) {

            editRecordName.setError(
                    "Recording name wajib diisi"
            );

            editRecordName.requestFocus();

            return;
        }


        recordName =
                sanitizeRecordName(
                        inputRecordName
                );


        if (recordName.isEmpty()) {

            editRecordName.setError(
                    "Recording name tidak valid"
            );

            editRecordName.requestFocus();

            return;
        }


        // -----------------------------------------------------
        // Validate PC IPv4
        // -----------------------------------------------------

        pcIpString =
                editPcIp
                        .getText()
                        .toString()
                        .trim();


        if (pcIpString.isEmpty()) {

            editPcIp.setError(
                    "PC IP wajib diisi"
            );

            editPcIp.requestFocus();

            return;
        }


        try {

            pcAddress =
                    InetAddress.getByName(
                            pcIpString
                    );

        } catch (Exception e) {

            editPcIp.setError(
                    "IP address tidak valid"
            );

            editPcIp.requestFocus();

            return;
        }


        // -----------------------------------------------------
        // Validate UDP port
        // -----------------------------------------------------

        String portString =
                editPcPort
                        .getText()
                        .toString()
                        .trim();


        try {

            pcPort =
                    Integer.parseInt(
                            portString
                    );

        } catch (NumberFormatException e) {

            editPcPort.setError(
                    "Port tidak valid"
            );

            editPcPort.requestFocus();

            return;
        }


        if (pcPort < 1
                || pcPort > 65535) {

            editPcPort.setError(
                    "Port harus 1-65535"
            );

            editPcPort.requestFocus();

            return;
        }


        // -----------------------------------------------------
        // Create session ID
        // -----------------------------------------------------

        sessionId =
                new SimpleDateFormat(

                        "yyyyMMdd_HHmmss_SSS",

                        Locale.US

                ).format(
                        new Date()
                );


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


        String suffix =
                recordName
                        + "_"
                        + sessionId;


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
        // Reset state
        // -----------------------------------------------------

        globalSeq = 0;
        accelSeq = 0;
        gyroSeq = 0;

        networkPacketsSent = 0;
        networkQueueDrops = 0;
        networkSendErrors = 0;

        writeQueue.clear();
        networkQueue.clear();


        // -----------------------------------------------------
        // Create local CSV
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
                    "ERROR creating local CSV"
            );

            return;
        }


        // -----------------------------------------------------
        // Initial metadata
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
        // Start network thread
        // -----------------------------------------------------

        networkRunning = true;
        networkReady = false;


        networkThread =
                new Thread(

                        this::networkLoop,

                        "IMUNetworkThread"
                );


        networkThread.start();


        // -----------------------------------------------------
        // Start acquisition
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


        txtNetworkCount.setText(

                "UDP sent: 0"
                        + "\nQueue drops: 0"
                        + "\nSend errors: 0"
        );


        txtNetwork.setText(

                "Network: STARTING"
                        + "\n"
                        + pcIpString
                        + ":"
                        + pcPort
        );


        txtFile.setText(

                "Local file:\n"
                        + currentFile
                        .getAbsolutePath()
        );


        editRecordName.setEnabled(false);
        editPcIp.setEnabled(false);
        editPcPort.setEnabled(false);

        btnStart.setEnabled(false);
        btnStop.setEnabled(true);
        btnDeleteLast.setEnabled(false);


        Log.i(

                TAG,

                "Session started"
                        + " name="
                        + recordName

                        + " session="
                        + sessionId

                        + " target="
                        + pcIpString
                        + ":"
                        + pcPort
        );
    }


    // =========================================================
    // SENSOR CALLBACK
    // =========================================================

    @Override
    public void onSensorChanged(
            SensorEvent event
    ) {

        if (!recording) {

            return;
        }


        long callbackElapsedNs =
                SystemClock
                        .elapsedRealtimeNanos();


        long sensorTimestampNs =
                event.timestamp;


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


        globalSeq++;


        float x =
                event.values[0];

        float y =
                event.values[1];

        float z =
                event.values[2];


        // -----------------------------------------------------
        // LOCAL LOGGER
        // -----------------------------------------------------

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


        writeQueue.offer(
                localRow
        );


        // -----------------------------------------------------
        // NETWORK QUEUE
        // -----------------------------------------------------

        NetworkSample networkSample =
                new NetworkSample(

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


        boolean queued =
                networkQueue.offer(
                        networkSample
                );


        if (!queued) {

            networkQueueDrops++;
        }


        // -----------------------------------------------------
        // UI counters
        // -----------------------------------------------------

        if (globalSeq % 200 == 0) {


            long total =
                    globalSeq;

            long acc =
                    accelSeq;

            long gyro =
                    gyroSeq;

            long sent =
                    networkPacketsSent;

            long dropped =
                    networkQueueDrops;

            long errors =
                    networkSendErrors;


            runOnUiThread(() -> {

                txtCount.setText(

                        "Total: "
                                + total

                                + "\nACC: "
                                + acc

                                + "\nGYRO: "
                                + gyro
                );


                txtNetworkCount.setText(

                        "UDP sent: "
                                + sent

                                + "\nQueue drops: "
                                + dropped

                                + "\nSend errors: "
                                + errors
                );
            });
        }
    }


    // =========================================================
    // LOCAL WRITER LOOP
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

                            "LOCAL written="
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

                    "Local writer I/O error",

                    e
            );


        } catch (InterruptedException e) {


            Thread.currentThread()
                    .interrupt();


            Log.e(

                    TAG,

                    "Local writer interrupted",

                    e
            );
        }
    }


    // =========================================================
    // UDP NETWORK LOOP
    // =========================================================

    private void networkLoop() {


        try {


            udpSocket =
                    new DatagramSocket();


            /*
             * Connected UDP socket:
             * tidak membuat TCP connection.
             * Ini hanya menetapkan default destination.
             */
            udpSocket.connect(
                    pcAddress,
                    pcPort
            );


            networkReady =
                    true;


            runOnUiThread(() ->

                    txtNetwork.setText(

                            "Network: STREAMING"
                                    + "\n"
                                    + pcIpString
                                    + ":"
                                    + pcPort
                    )
            );


            Log.i(

                    TAG,

                    "UDP socket ready -> "
                            + pcIpString
                            + ":"
                            + pcPort
            );


            while (networkRunning
                    || !networkQueue.isEmpty()) {


                NetworkSample sample =
                        networkQueue.poll(

                                100,

                                TimeUnit.MILLISECONDS
                        );


                if (sample == null) {

                    continue;
                }


                long sendElapsedNs =
                        SystemClock
                                .elapsedRealtimeNanos();


                /*
                 * Packet schema:
                 *
                 * DATA
                 * protocol_version
                 * session_id
                 * record_name
                 * seq_global
                 * seq_sensor
                 * sensor_type
                 * sensor_ts_phone_ns
                 * callback_elapsed_ns
                 * send_elapsed_ns
                 * x
                 * y
                 * z
                 * accuracy
                 */

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


                byte[] payload =
                        message.getBytes(
                                StandardCharsets.UTF_8
                        );


                DatagramPacket packet =
                        new DatagramPacket(

                                payload,

                                payload.length
                        );


                try {


                    udpSocket.send(
                            packet
                    );


                    networkPacketsSent++;


                } catch (IOException e) {


                    networkSendErrors++;


                    Log.e(

                            TAG,

                            "UDP send error",

                            e
                    );
                }
            }


        } catch (Exception e) {


            networkReady =
                    false;


            networkSendErrors++;


            Log.e(

                    TAG,

                    "UDP network initialization error",

                    e
            );


            runOnUiThread(() ->

                    txtNetwork.setText(
                            "Network: ERROR"
                    )
            );


        } finally {


            networkReady =
                    false;


            if (udpSocket != null) {


                udpSocket.close();

                udpSocket =
                        null;
            }


            Log.i(

                    TAG,

                    "UDP thread stopped"
                            + " sent="
                            + networkPacketsSent

                            + " queueDrops="
                            + networkQueueDrops

                            + " sendErrors="
                            + networkSendErrors
            );
        }
    }


    // =========================================================
    // STOP
    // =========================================================

    private void stopRecording() {


        if (!recording) {

            return;
        }


        // -----------------------------------------------------
        // Stop sensor source first
        // -----------------------------------------------------

        recording =
                false;


        sensorManager.unregisterListener(
                this
        );


        // -----------------------------------------------------
        // Drain local writer queue
        // -----------------------------------------------------

        writerRunning =
                false;


        if (writerThread != null) {


            try {


                writerThread.join(
                        5000
                );


            } catch (InterruptedException e) {


                Thread.currentThread()
                        .interrupt();
            }
        }


        // -----------------------------------------------------
        // Drain network queue
        // -----------------------------------------------------

        networkRunning =
                false;


        if (networkThread != null) {


            try {


                networkThread.join(
                        5000
                );


            } catch (InterruptedException e) {


                Thread.currentThread()
                        .interrupt();
            }
        }


        // -----------------------------------------------------
        // Close local CSV
        // -----------------------------------------------------

        try {


            if (writer != null) {


                writer.flush();

                writer.close();

                writer =
                        null;
            }


        } catch (IOException e) {


            Log.e(

                    TAG,

                    "Error closing local CSV",

                    e
            );
        }


        // -----------------------------------------------------
        // Append final metadata
        // -----------------------------------------------------

        appendFinalMetadata();


        // -----------------------------------------------------
        // Freeze counters for UI
        // -----------------------------------------------------

        long finalGlobal =
                globalSeq;


        long finalAccel =
                accelSeq;


        long finalGyro =
                gyroSeq;


        long finalSent =
                networkPacketsSent;


        long finalQueueDrops =
                networkQueueDrops;


        long finalSendErrors =
                networkSendErrors;


        String finishedName =
                recordName;


        // -----------------------------------------------------
        // UI
        // -----------------------------------------------------

        txtStatus.setText(

                "STOPPED\n"
                        + finishedName
        );


        txtNetwork.setText(

                "Network: STOPPED"
        );


        txtCount.setText(

                "Total: "
                        + finalGlobal

                        + "\nACC: "
                        + finalAccel

                        + "\nGYRO: "
                        + finalGyro
        );


        txtNetworkCount.setText(

                "UDP sent: "
                        + finalSent

                        + "\nQueue drops: "
                        + finalQueueDrops

                        + "\nSend errors: "
                        + finalSendErrors
        );


        editRecordName.setEnabled(
                true
        );

        editPcIp.setEnabled(
                true
        );

        editPcPort.setEnabled(
                true
        );


        editRecordName.setText(
                ""
        );


        btnStart.setEnabled(
                true
        );

        btnStop.setEnabled(
                false
        );


        updateLastSessionUI();
        updateDeleteButtonState();


        Log.i(

                TAG,

                "Session stopped"
                        + " name="
                        + finishedName

                        + " total="
                        + finalGlobal

                        + " ACC="
                        + finalAccel

                        + " GYRO="
                        + finalGyro

                        + " localQueue="
                        + writeQueue.size()

                        + " UDPsent="
                        + finalSent

                        + " networkQueue="
                        + networkQueue.size()

                        + " networkQueueDrops="
                        + finalQueueDrops

                        + " sendErrors="
                        + finalSendErrors
        );


        Toast.makeText(

                this,

                "Session tersimpan: "
                        + finishedName,

                Toast.LENGTH_SHORT

        ).show();
    }


    // =========================================================
    // INITIAL METADATA
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


            metadataWriter.write(
                    "udp_protocol_version="
                            + UDP_PROTOCOL_VERSION
                            + "\n"
            );


            metadataWriter.write(
                    "udp_target_ip="
                            + pcIpString
                            + "\n"
            );


            metadataWriter.write(
                    "udp_target_port="
                            + pcPort
                            + "\n"
            );


            if (accelerometer != null) {


                metadataWriter.write(
                        "accelerometer_name="
                                + accelerometer.getName()
                                + "\n"
                );


                metadataWriter.write(
                        "accelerometer_vendor="
                                + accelerometer.getVendor()
                                + "\n"
                );


                metadataWriter.write(
                        "accelerometer_version="
                                + accelerometer.getVersion()
                                + "\n"
                );


                metadataWriter.write(
                        "accelerometer_resolution="
                                + accelerometer.getResolution()
                                + "\n"
                );


                metadataWriter.write(
                        "accelerometer_max_range="
                                + accelerometer.getMaximumRange()
                                + "\n"
                );


                metadataWriter.write(
                        "accelerometer_min_delay_us="
                                + accelerometer.getMinDelay()
                                + "\n"
                );
            }


            if (gyroscope != null) {


                metadataWriter.write(
                        "gyroscope_name="
                                + gyroscope.getName()
                                + "\n"
                );


                metadataWriter.write(
                        "gyroscope_vendor="
                                + gyroscope.getVendor()
                                + "\n"
                );


                metadataWriter.write(
                        "gyroscope_version="
                                + gyroscope.getVersion()
                                + "\n"
                );


                metadataWriter.write(
                        "gyroscope_resolution="
                                + gyroscope.getResolution()
                                + "\n"
                );


                metadataWriter.write(
                        "gyroscope_max_range="
                                + gyroscope.getMaximumRange()
                                + "\n"
                );


                metadataWriter.write(
                        "gyroscope_min_delay_us="
                                + gyroscope.getMinDelay()
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
    // FINAL METADATA
    // =========================================================

    private void appendFinalMetadata() {


        if (metadataFile == null) {

            return;
        }


        try (
                BufferedWriter metadataWriter =

                        new BufferedWriter(

                                new FileWriter(

                                        metadataFile,

                                        true
                                )
                        )
        ) {


            metadataWriter.write(
                    "final_total_samples="
                            + globalSeq
                            + "\n"
            );


            metadataWriter.write(
                    "final_acc_samples="
                            + accelSeq
                            + "\n"
            );


            metadataWriter.write(
                    "final_gyro_samples="
                            + gyroSeq
                            + "\n"
            );


            metadataWriter.write(
                    "final_udp_packets_sent="
                            + networkPacketsSent
                            + "\n"
            );


            metadataWriter.write(
                    "final_network_queue_drops="
                            + networkQueueDrops
                            + "\n"
            );


            metadataWriter.write(
                    "final_udp_send_errors="
                            + networkSendErrors
                            + "\n"
            );


            metadataWriter.write(
                    "final_local_queue_remaining="
                            + writeQueue.size()
                            + "\n"
            );


            metadataWriter.write(
                    "final_network_queue_remaining="
                            + networkQueue.size()
                            + "\n"
            );


        } catch (IOException e) {


            Log.e(

                    TAG,

                    "Cannot append final metadata",

                    e
            );
        }
    }


    // =========================================================
    // RECORD NAME SANITIZATION
    // =========================================================

    private String sanitizeRecordName(
            String input
    ) {


        String cleaned =
                input
                        .trim()
                        .toLowerCase(
                                Locale.US
                        );


        cleaned =
                cleaned.replaceAll(
                        "\\s+",
                        "_"
                );


        cleaned =
                cleaned.replaceAll(
                        "[^a-z0-9_-]",
                        ""
                );


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

                getExternalFilesDir(
                        null
                ),

                "sessions"
        );
    }


    // =========================================================
    // FIND LATEST LOCAL IMU FILE
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


            if (!name.startsWith(
                    "imu_"
            )
                    || !name.endsWith(
                    ".csv"
            )) {

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
    // FIND MATCHING METADATA
    // =========================================================

    private File findMatchingMetadataFile(
            File imuFile
    ) {


        if (imuFile == null) {

            return null;
        }


        String imuName =
                imuFile.getName();


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
    // READ RECORD NAME FROM META
    // =========================================================

    private String readRecordNameFromMetadata(
            File metaFile
    ) {


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
                    (line =
                            reader.readLine())
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
    // UPDATE DELETE BUTTON
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


        File latest =
                findLatestImuFile();


        btnDeleteLast.setEnabled(
                latest != null
        );
    }


    // =========================================================
    // UPDATE LAST SESSION
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


        String lastName =
                readRecordNameFromMetadata(
                        metaFile
                );


        txtLastSession.setText(

                "Last local session:\n"
                        + lastName

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
                    "No local recording available"
            );


            updateDeleteButtonState();

            return;
        }


        File metaFile =
                findMatchingMetadataFile(
                        imuFile
                );


        String lastName =
                readRecordNameFromMetadata(
                        metaFile
                );


        new AlertDialog.Builder(
                this
        )

                .setTitle(
                        "Delete Last Local Recording?"
                )

                .setMessage(

                        "Recording:\n"
                                + lastName

                                + "\n\nCSV:\n"
                                + imuFile.getName()

                                + "\n\nMetadata:\n"
                                + (
                                metaFile != null
                                        ? metaFile.getName()
                                        : "-"
                        )

                                + "\n\n"
                                + "PC receiver log tidak ikut dihapus."
                )

                .setNegativeButton(
                        "CANCEL",
                        null
                )

                .setPositiveButton(

                        "DELETE",

                        (dialog, which) ->

                                deleteSession(

                                        lastName,

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
            File metaFile
    ) {


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


    // =========================================================
    // DELETION AUDIT
    // =========================================================

    private void writeDeletionAudit(
            String deletedRecordName,
            File imuFile,
            File metaFile
    ) {


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
            int accuracy
    ) {


        Log.i(

                TAG,

                "Accuracy: "
                        + sensor.getName()

                        + " = "
                        + accuracy
        );
    }


    // =========================================================
    // LIFECYCLE
    // =========================================================

    @Override
    protected void onPause() {

        super.onPause();


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