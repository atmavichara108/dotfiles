---
type: sysop-task
status: proposed
role: sysop
project: AndroidOS
---

# Sysop Task: AndroidOS Environment Preparation

## Цель

Подготовить и документировать окружение для AndroidOS на Manjaro. Это read-first аудит и proposal, не реализация AndroidOS, не сборка application code и не автоматическая установка.

## Правила выполнения

1. Сначала зафиксировать current state и package-manager convention dotfiles/Manjaro; не выполнять `pacman -S`, `yay`, `paru`, `sudo`, правки `/etc`, udev или permissions без отдельного подтверждения пользователя.
2. Не удалять, не перезаписывать и не менять системные сервисы; сохранить rollback plan и список exact changes before approval.
3. После подтверждения выполнять только согласованные изменения, минимально и обратимо; секреты, device data, audio и transcripts не копировать в repo.

## Read-first inventory

Проверить наличие и версии: JDK (`java`, `javac`), Android SDK root и command-line tools, `platform-tools`/`adb`, build-tools, Gradle wrapper/system Gradle, Kotlin/Gradle compatibility, OpenCode и AndroidOS project-local agents/commands. Проверить `pacman -Q` только read-only, `$PATH`, `JAVA_HOME`, `ANDROID_HOME`/`ANDROID_SDK_ROOT`, disk/RAM, USB devices and `adb devices`.

Проверить Manjaro package policy, active user groups, existing udev rules, USB permissions, SELinux/polkit assumptions where applicable, and whether current dotfiles already manage any of these. Do not infer that a missing command warrants installation.

## Proposal scope after approval

- JDK version suitable for selected Android Gradle Plugin.
- Android SDK command-line tools, required platform and build-tools.
- `platform-tools`/ADB and device authorization for physical phone.
- Gradle strategy: project wrapper preferred; Kotlin/Gradle/AGP compatibility recorded, no global upgrade by default.
- udev rules and USB permissions only if the read-only diagnosis proves they are needed; record ownership, mode and rollback.
- Physical-device baseline: model/API/build, `adb` authorization, install/debug/logcat capability, battery/thermal constraints.
- Optional emulator only as explicitly approved secondary check; physical device remains baseline.
- OpenCode integration: confirm AndroidOS `.opencode/agents` and `.opencode/command` resolve real local roles; sysop remains global dotfiles role and does not edit AndroidOS code.

## Required report artifact

Write a proposed report (path agreed with user, preferably outside AndroidOS private data) containing timestamp, host/tool versions, missing prerequisites, compatibility matrix, device baseline, commands actually run, changes approved/performed, rollback steps, and unresolved decisions. Mark every unverified item `[проверить]`; do not claim environment ready until a sample build/ADB check is accepted by the user.

## Handoff

Return the report to Max and stop for approval before any install/configure action. After environment setup, AndroidOS `TASKS.md` task `P0-07` becomes actionable for the real-device benchmark.
