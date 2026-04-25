# Zapret2 Manager

Zapret2 Manager - это Windows-приложение, которое собирает в один понятный интерфейс zapret/zapret2, готовые стратегии Flowseal, blockcheck и Telegram WebSocket proxy.

Идея проекта: обычный пользователь скачивает ZIP, запускает EXE, выбирает профиль и получает кнопку “запустить/остановить”, а разработчики могут улучшать стратегии, упаковку, updater, интерфейс и диагностику.

## Текущий статус

Это ранняя версия для Windows 10/11. Приложение уже можно собирать и отдавать как portable ZIP, но кодовая база ещё нуждается в рефакторинге и тестах.

Windows 7 сейчас не является основной целью.

## Что умеет приложение

- Запускает и останавливает DPI-стратегии через `winws2.exe`.
- Содержит встроенные профили и профили на базе Flowseal.
- Управляет Telegram WebSocket proxy.
- Сворачивается в трей и может работать фоном.
- При полном выходе пытается остановить связанные процессы.
- Проверяет обновления `zapret`, `zapret2`, Flowseal-стратегий и `tg-ws-proxy`.
- Собирается в portable-релиз без необходимости ставить Python пользователю.

## Важно

Это не оригинальный `zapret`, `zapret2`, Flowseal или `tg-ws-proxy`. Это оболочка-комбайн над чужими проектами.

Приложение использует WinDivert и требует прав администратора. Антивирусы и SmartScreen могут ругаться на неподписанный EXE или сетевой драйвер.

## Для пользователя

1. Скачайте ZIP из GitHub Releases.
2. Распакуйте в обычную папку, например `C:\Tools\Zapret2Manager`.
3. Запустите `Zapret2Manager.exe`.
4. Разрешите запуск от администратора.
5. Выберите профиль во вкладке `Конфигурации`.
6. Нажмите запуск.
7. Если что-то пошло не так, нажмите остановить или полностью выйдите через трей.

Не запускайте приложение прямо из ZIP.

## Для разработчика

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements-dev.txt
python main.py
```

Проверка перед pull request:

```powershell
python -m py_compile main.py core.py ui.py upstreams.py tg_ws_proxy.py flowseal_profiles.py generator.py prepare_release_assets.py
```

Сборка portable-релиза:

```powershell
python prepare_release_assets.py
.\build_release.bat
```

Результат:

```text
dist_win1011\Zapret2Manager
```

## Что не коммитить

Не нужно коммитить `build*`, `dist*`, ZIP-архивы, `zapret/`, `data/upstreams/`, логи, личные настройки и сгенерированные hostlist-файлы.

Исходный репозиторий должен быть лёгким. Готовые бинарные сборки лучше публиковать через GitHub Releases.

## Куда смотреть

- [README.md](README.md) - английская стартовая страница.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - устройство проекта.
- [docs/RELEASE.md](docs/RELEASE.md) - чеклист релиза.
- [CONTRIBUTING.md](CONTRIBUTING.md) - правила для pull request.
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) - сторонние компоненты и лицензии.

## Upstream-проекты

- https://github.com/bol-van/zapret-win-bundle
- https://github.com/bol-van/zapret2
- https://github.com/Flowseal/zapret-discord-youtube
- https://github.com/Flowseal/tg-ws-proxy
- https://github.com/basil00/WinDivert
