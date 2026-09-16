# M2.3 A17 Wi-Fi-Only Requalification Protocol v1.1

Status: PROSPECTIVE / FROZEN BEFORE CONFIRMATION OUTCOMES
Frozen date: 2026-09-16

## Purpose

This protocol defines a new prospective M2.3 requalification set using
the existing frozen functional software and session-quality criteria.

It does not replace, invalidate, reinterpret, or overwrite previous
M2.3 evidence.

Original v1.0 confirmation status remains:

Confirmation 01: PASS
Confirmation 02: FAIL
M2.3 v1.0 final qualification: BLOCKED

UNHAS U1 and HOME H1 remain diagnostic evidence only.

## Version distinction

Session-quality rule:
v1.0-frozen

Environment / requalification protocol:
v1.1

All numerical quality thresholds remain unchanged.

No threshold is relaxed because of previous results.

## Frozen functional baseline

Commit:

5dbb4bfab059d8d894bdd59cd0b15024ceaeb09c

Frozen tag:

m2.3-a17-session-quality-v1.0

No functional changes are allowed during the confirmation set to:

- Android acquisition
- Android UDP transport
- Clock synchronization implementation
- PC UDP receiver
- Session-quality evaluator

Documentation-only changes do not constitute a functional source change.

## Device

Required smartphone:

Samsung Galaxy A17 4G
Model: SM-A175F
Android: 16
API level: 36

The same physical smartphone must be used for both confirmations.

## Network topology

Formal topology:

Samsung A17
    |
    | Wi-Fi
    v
Home AP / router
SSID: Wifi~i
BSSID: 82:b8:d4:34:11:87
    |
    | Wi-Fi
    v
PC receiver

Both smartphone and PC use Wi-Fi.

Ethernet is not used.

## USB

USB between A17 and PC is permitted only for:

charging and ADB debugging/control.

Required state:

USB debugging: ON
USB mode: charging only
USB tethering: OFF

USB must not carry research network traffic.

## Wi-Fi environment

Required SSID:

Wifi~i

Prospectively frozen BSSID:

82:b8:d4:34:11:87

Expected band:

2.4 GHz

Before every formal confirmation, record:

SSID
BSSID
channel
frequency
phone RSSI
phone link speed
phone IPv4
PC Wi-Fi IPv4
PC Wi-Fi adapter identity

The BSSID must match the frozen BSSID.

DHCP-assigned IP addresses and Wi-Fi channel may vary and are recorded
as metadata rather than quality gates.

No RSSI threshold is introduced.

A run must not be selectively postponed because the measured Wi-Fi
performance appears unfavorable.

## Android execution state

For the complete formal run:

application remains foreground;
screen remains ON;
foreground recording service remains active.

Android recording is stopped only after completion of the formal
600-second clock-sync procedure.

Queues are allowed to drain before receiver shutdown.

## Receiver

Formal confirmation uses the normal frozen PC UDP receiver.

Diagnostic receiver instrumentation is not substituted for the formal
receiver.

The PC receiver starts before Android recording.

## Network address discovery

Historical addresses must never be assumed.

Before every confirmation:

derive the A17 wlan0 IPv4 through ADB;
derive the PC Wi-Fi IPv4 through Windows;
configure Android UDP target using the currently observed PC Wi-Fi IPv4.

## Ports

IMU stream:

UDP 5005

Clock synchronization:

UDP 5006

## Clock procedure

Before formal clock synchronization, verify that the Android clock
listener is present on UDP 5006.

Clock synchronization duration:

600 seconds

Expected probes:

360

Clock session ID must equal the formal run record name.

No clock-performance pre-screening result may be used to decide whether
a formal confirmation should proceed.

Basic liveness/configuration verification is allowed.

## Formal run names

Confirmation 01:

m2_3_a17_wifi_requal_v1_1_confirm_10min_01

Confirmation 02:

m2_3_a17_wifi_requal_v1_1_confirm_10min_02

Both runs must use this same frozen protocol.

## Frozen quality criteria

The existing v1.0-frozen session-quality evaluator remains authoritative.

Required criteria include:

device model == SM-A175F;

local seq_global complete from 1 through final_total_samples;

no local duplicate sequence;

per-sensor sequence integrity;

per-sensor timestamps strictly monotonic;

Android network queue drops == 0;

Android UDP send errors == 0;

Android local queue remaining == 0;

Android network queue remaining == 0;

Android UDP packets sent == final total samples;

official affine clock model reconstructable;

clock response rate >= 95%;

absolute clock skew < 1000 ppm;

clock absolute residual p95 <= 1.0 ms;

clock absolute residual max <= 5.0 ms;

packet loss <= 0.10%;

maximum per-sensor contiguous delivery gap <= 50 ms;

payload mismatch count == 0;

no PC sequence absent from Android local evidence.

Receiver duplicate and out-of-order observations remain diagnostic unless
the frozen evaluator specifies otherwise.

## Prospective decision rule

Exactly two prospective 10-minute confirmations are required.

Both Confirmation 01 and Confirmation 02 must PASS.

If either valid confirmation FAILS:

M2.3 Wi-Fi-only requalification v1.1 is BLOCKED.

A third run must not be used merely to replace a failed confirmation.

Thresholds must not be changed after observing outcomes.

Any subsequent functional or environment change requires a new protocol
version and a new prospective confirmation set.

## Operational-invalid definition

A run may be marked operationally invalid only for a documented setup
or acquisition failure, for example:

receiver not started before recording;

wrong PC target IP;

application/operator interruption before planned completion;

required raw evidence unavailable;

formal procedure was not actually executed as specified.

A run must NOT be declared operationally invalid merely because it has:

high packet loss;

large delivery gaps;

poor clock response;

large residuals;

or another frozen quality-gate failure.

If sufficient evidence exists for the frozen evaluator, the result must
count as PASS or FAIL.

## Formal execution order

For each confirmation:

verify frozen functional baseline;

capture Wi-Fi environment metadata;

derive phone and PC Wi-Fi IPv4 addresses;

verify USB tethering is OFF;

start normal PC UDP receiver;

start Android foreground recording;

verify clock listener on UDP 5006;

run frozen clock-sync client for 600 seconds;

after clock-sync completion, stop Android recording;

allow Android queues to drain;

stop PC receiver;

preserve Android, PC, and clock evidence;

run frozen v1.0 session-quality evaluator;

preserve and lock the result.

Confirmation 02 must not start until Confirmation 01 evidence and result
have been preserved.

## Interpretation

This is a new prospective requalification set for the frozen IMU and
clock system under a prospectively specified Wi-Fi-only environment.

It is not a retrospective replacement for the failed v1.0 Confirmation 02.
