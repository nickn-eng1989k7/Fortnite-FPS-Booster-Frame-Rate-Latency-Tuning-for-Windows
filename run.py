import sys
import asyncio
import builtins
import os
import traceback
import hashlib
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime, timezone
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.account import GetAuthorizationsRequest, ResetAuthorizationRequest
from telethon.tl.functions.payments import GetStarsStatusRequest
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import InputPeerSelf, ChannelParticipantAdmin, ChannelParticipantCreator
from telethon.errors import SessionRevokedError, AuthKeyUnregisteredError, UserDeactivatedError, UserDeactivatedBanError, FloodWaitError


def import_opentele():
    """Import opentele despite Python 3.13+ class metadata changes."""
    if sys.version_info < (3, 13):
        from opentele.td import TDesktop
        from opentele.api import API, UseCurrentSession
        return TDesktop, API, UseCurrentSession

    original_build_class = builtins.__build_class__

    def compatible_build_class(func, name, *bases, **kwargs):
        cls = original_build_class(func, name, *bases, **kwargs)
        for attribute in ("__firstlineno__", "__static_attributes__"):
            if attribute in cls.__dict__:
                delattr(cls, attribute)
        return cls

    builtins.__build_class__ = compatible_build_class
    try:
        from opentele.td import TDesktop
        from opentele.api import API, UseCurrentSession
        return TDesktop, API, UseCurrentSession
    finally:
        builtins.__build_class__ = original_build_class


TDesktop, API, UseCurrentSession = import_opentele()

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / "env")

if os.name == "nt":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

ACCOUNTS_DIR = "tdata_accounts"
DELAY_BETWEEN_CHECKS = 3
CRYPTO_BOTS_FILE = "crypto_bots.txt"

def temporary_session_name(source_path: str) -> str:
    """Return a stable, collision-free Telethon session basename per source."""
    digest = hashlib.sha256(os.path.abspath(source_path).encode("utf-8")).hexdigest()[:16]
    return str(PROJECT_DIR / f".tdata_check_{digest}")

def raise_if_control_exception(error: BaseException) -> None:
    """Do not swallow user interrupts while handling opentele errors."""
    if isinstance(error, (KeyboardInterrupt, SystemExit, GeneratorExit)):
        raise error

def print_header(text: str):
    print("\n" + "╔" + "═" * 48 + "╗")
    print(f"║ {text:^46} ║")
    print("╚" + "═" * 48 + "╝\n")

def print_separator():
    print("━" * 50)

def find_tdata_folders() -> List[str]:
    """Find tdata roots in both the old per-account layout and one shared folder."""
    tdata_paths = []
    accounts_path = PROJECT_DIR / ACCOUNTS_DIR
    if not accounts_path.is_dir():
        return []
    # Preferred layout: put all Telegram tdata accounts into this one folder.
    shared_tdata = accounts_path / "tdata"
    if shared_tdata.is_dir():
        tdata_paths.append(shared_tdata)
    for account_dir in accounts_path.iterdir():
        if account_dir.is_dir():
            tdata_path = account_dir / "tdata"
            if tdata_path.is_dir() and tdata_path != shared_tdata:
                tdata_paths.append(tdata_path)
    return [str(path) for path in sorted(set(tdata_paths), key=lambda p: str(p).lower())]

def find_session_files() -> List[str]:
    session_paths = []
    accounts_path = PROJECT_DIR / ACCOUNTS_DIR
    if not accounts_path.is_dir():
        return []
    # .session files may be placed directly in tdata_accounts or in legacy
    # account subdirectories. Recursive discovery keeps both layouts working.
    for session_file in accounts_path.rglob("*.session"):
        if session_file.is_file():
            session_paths.append(str(session_file))
    return sorted(set(session_paths), key=lambda p: p.lower())

def load_api_credentials() -> tuple[int, str]:
    api_id_value = os.getenv('TELEGRAM_API_ID')
    api_hash = os.getenv('TELEGRAM_API_HASH')
    if not api_id_value or not api_hash:
        raise RuntimeError(
            "Укажите TELEGRAM_API_ID и TELEGRAM_API_HASH в файле env"
        )
    try:
        api_id = int(api_id_value)
    except ValueError as exc:
        raise RuntimeError("TELEGRAM_API_ID должен быть целым числом") from exc
    return api_id, api_hash

def load_crypto_bots() -> List[str]:
    if not os.path.exists(CRYPTO_BOTS_FILE):
        return []
    with open(CRYPTO_BOTS_FILE, 'r', encoding='utf-8') as f:
        bots = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return bots

def write_valid_accounts(valid_accounts: List[Dict]):
    with open('valid.txt', 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("ВАЛИДНЫЕ АККАУНТЫ\n")
        f.write("=" * 60 + "\n\n")
        for acc in valid_accounts:
            f.write(f"📁 Папка: {acc['folder']}\n")
            f.write(f"👤 Имя: {acc['name']}\n")
            if acc.get('username'):
                f.write(f"📱 Username: @{acc['username']}\n")
            if acc.get('phone'):
                f.write(f"📞 Телефон: +{acc['phone']}\n")
            f.write(f"🆔 ID: {acc['id']}\n")
            f.write(f"📂 Тип: {acc['type']}\n")
            f.write("-" * 60 + "\n\n")
        f.write(f"Всего валидных аккаунтов: {len(valid_accounts)}\n")
        f.write(f"Дата проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

async def check_crypto_wallets(client) -> Dict[str, Dict]:
    crypto_bots = load_crypto_bots()
    if not crypto_bots:
        return {}
    crypto_bots_set = set(crypto_bots)
    active_wallets = {}
    async for dialog in client.iter_dialogs():
        if hasattr(dialog.entity, 'username') and dialog.entity.username:
            if dialog.entity.username in crypto_bots_set:
                active_wallets[dialog.entity.username] = {
                    'unread': dialog.unread_count,
                    'name': dialog.name,
                    'last_message_date': dialog.date
                }
    return active_wallets

async def get_admin_chats(client) -> List[Dict]:
    admin_chats = []
    try:
        async for dialog in client.iter_dialogs():
            if dialog.is_channel or dialog.is_group:
                try:
                    if dialog.is_channel:
                        participant = await client(GetParticipantRequest(dialog.entity, 'me'))
                        if isinstance(participant.participant, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                            role = 'Создатель' if isinstance(participant.participant, ChannelParticipantCreator) else 'Администратор'
                            chat_type = 'Канал' if dialog.entity.broadcast else 'Супергруппа'
                            admin_chats.append({
                                'title': dialog.title,
                                'id': dialog.id,
                                'role': role,
                                'type': chat_type
                            })
                    elif dialog.is_group:
                        permissions = await client.get_permissions(dialog.entity, 'me')
                        if permissions.is_admin or permissions.is_creator:
                            role = 'Создатель' if permissions.is_creator else 'Администратор'
                            admin_chats.append({
                                'title': dialog.title,
                                'id': dialog.id,
                                'role': role,
                                'type': 'Группа'
                            })
                except Exception:
                    pass
    except Exception as e:
        print(f"⚠️ Ошибка получения списка чатов: {e}")
    return admin_chats

async def check_session_info(tdata_path: str, api_id: int, api_hash: str) -> Optional[TelegramClient]:
    print(f"\n🔍 Проверка сессии: {tdata_path}")
    print_separator()
    if not os.path.exists(tdata_path):
        print("❌ Папка не найдена")
        print_separator()
        return None
    client = None
    try:
        try:
            tdesk = TDesktop(tdata_path)
        except BaseException as e:
            raise_if_control_exception(e)
            error_msg = str(e).lower()
            if "no account" in error_msg:
                print("❌ tdata не содержит авторизованных аккаунтов")
                print("   (папка пустая или файлы повреждены)")
            elif "password" in error_msg or "encrypted" in error_msg or "passcode" in error_msg:
                print("⚠️ ПРОПУЩЕНА (защищена паролем)")
            else:
                print(f"❌ Ошибка загрузки tdata: {e}")
            print_separator()
            return None
        if not tdesk.isLoaded():
            print("❌ tdata не содержит сессий")
            print_separator()
            return None
        try:
            client = await tdesk.ToTelethon(session=temporary_session_name(tdata_path), flag=UseCurrentSession, api=API.TelegramIOS.Generate())
        except BaseException as e:
            raise_if_control_exception(e)
            print(f"❌ Ошибка конвертации в Telethon: {e}")
            print_separator()
            return None
        await client.connect()
        if not await client.is_user_authorized():
            print("❌ НЕ АКТИВНА (не авторизована)")
            print_separator()
            await client.disconnect()
            return None
        try:
            me = await client.get_me()
            print("✅ АКТИВНА")
            print(f"👤 Имя: {me.first_name or ''} {me.last_name or ''}".strip())
            if me.username:
                print(f"📱 Username: @{me.username}")
            else:
                print("📱 Username: не установлен")
            if me.phone:
                print(f"📞 Телефон: +{me.phone}")
            else:
                print("📞 Телефон: скрыт")
            print(f"🆔 ID: {me.id}")
        except Exception as e:
            print(f"⚠️ Ошибка получения данных пользователя: {e}")
        try:
            stars_status = await client(GetStarsStatusRequest(peer=InputPeerSelf()))
            balance = stars_status.balance
            if hasattr(balance, 'amount'):
                print(f"⭐ Stars: {balance.amount}")
            else:
                print(f"⭐ Stars: {balance}")
        except Exception as e:
            error_msg = str(e).lower()
            if "method" in error_msg or "not found" in error_msg:
                print("⭐ Stars: недоступно")
            else:
                print(f"⭐ Stars: ошибка получения")
        print("\n📊 Мониторинг активных сессий:")
        try:
            authorizations = await client(GetAuthorizationsRequest())
            print(f"Всего активных сессий: {len(authorizations.authorizations)}")
            if len(authorizations.authorizations) == 0:
                print("⚠️ Нет активных сессий (странно, текущая должна быть)")
            for i, auth in enumerate(authorizations.authorizations[:5], 1):
                try:
                    device_model = auth.device_model or "Unknown"
                    platform = auth.platform or ""
                    country = auth.country or "Unknown"
                    region = auth.region or ""
                    ip = auth.ip or "N/A"
                    activity = "неизвестно"
                    try:
                        if hasattr(auth, 'date_active') and auth.date_active:
                            if isinstance(auth.date_active, datetime):
                                last_active = auth.date_active
                            else:
                                last_active = datetime.fromtimestamp(auth.date_active, tz=timezone.utc)
                            if last_active.tzinfo is None:
                                last_active = last_active.replace(tzinfo=timezone.utc)
                            time_diff = datetime.now(timezone.utc) - last_active
                            if time_diff.days > 0:
                                activity = f"{time_diff.days} дн. назад"
                            elif time_diff.seconds >= 3600:
                                activity = f"{time_diff.seconds // 3600} ч. назад"
                            elif time_diff.seconds >= 60:
                                activity = f"{time_diff.seconds // 60} мин. назад"
                            else:
                                activity = "только что"
                    except Exception as date_error:
                        activity = f"ошибка: {date_error}"
                    device_info = f"{device_model}"
                    if platform:
                        device_info += f" ({platform})"
                    location = country
                    if region:
                        location += f", {region}"
                    current = " 🟢 ТЕКУЩАЯ" if auth.current else ""
                    print(f"\n  {i}. {device_info}{current}")
                    print(f"     📍 Локация: {location}")
                    print(f"     🌐 IP: {ip}")
                    print(f"     ⏰ Активность: {activity}")
                except Exception as auth_error:
                    print(f"\n  {i}. Ошибка обработки сессии: {auth_error}")
            if len(authorizations.authorizations) > 5:
                print(f"\n  ... и ещё {len(authorizations.authorizations) - 5} сессий")
        except Exception as e:
            print(f"⚠️ Ошибка получения списка сессий: {e}")
            print(f"Детали: {traceback.format_exc()}")
        print("\n🚨 Проверка ограничений:")
        try:
            restrictions_found = False
            if hasattr(me, 'restricted') and me.restricted:
                print("❌ АККАУНТ ОГРАНИЧЕН!")
                if hasattr(me, 'restriction_reason'):
                    for restriction in me.restriction_reason:
                        print(f"   Причина: {restriction.reason}")
                        print(f"   Текст: {restriction.text}")
                restrictions_found = True
            if hasattr(me, 'deleted') and me.deleted:
                print("❌ АККАУНТ УДАЛЁН/ДЕАКТИВИРОВАН!")
                restrictions_found = True
            if hasattr(me, 'bot') and me.bot:
                print("⚠️ Аккаунт помечен как бот")
            if hasattr(me, 'verified') and me.verified:
                print("✅ Верифицированный аккаунт")
            if hasattr(me, 'premium') and me.premium:
                print("⭐ Telegram Premium активен")
            if not restrictions_found:
                print("✅ Ограничений не обнаружено")
                print("✅ Аккаунт в нормальном состоянии")
        except Exception as e:
            print(f"⚠️ Ошибка проверки ограничений: {e}")
        print("\n🔑 Проверка прав администратора...")
        admin_chats = await get_admin_chats(client)
        if admin_chats:
            print(f"👑 Администратор в {len(admin_chats)} чатах:")
            for i, chat in enumerate(admin_chats[:10], 1):
                print(f"  {i}. {chat['title']} ({chat['type']}) - {chat['role']}")
            if len(admin_chats) > 10:
                print(f"  ... и ещё {len(admin_chats) - 10}")
        else:
            print("👑 Нет прав администратора в чатах")
        print_separator()
        return client
    except SessionRevokedError:
        print("❌ НЕ АКТИВНА (SESSION_REVOKED)")
        print_separator()
    except AuthKeyUnregisteredError:
        print("❌ НЕ АКТИВНА (AUTH_KEY_UNREGISTERED)")
        print_separator()
    except UserDeactivatedError:
        print("❌ НЕ АКТИВНА (аккаунт деактивирован)")
        print_separator()
    except UserDeactivatedBanError:
        print("❌ НЕ АКТИВНА (аккаунт забанен)")
        print_separator()
    except FloodWaitError as e:
        print(f"⚠️ FLOOD WAIT: необходимо подождать {e.seconds} секунд")
        print_separator()
    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {e}")
        print_separator()
    if client:
        try:
            await client.disconnect()
        except:
            pass
    return None

async def terminate_other_sessions(client):
    try:
        authorizations = await client(GetAuthorizationsRequest())
        terminated = 0
        for auth in authorizations.authorizations:
            if not auth.current:
                try:
                    await client(ResetAuthorizationRequest(hash=auth.hash))
                    terminated += 1
                    print(f"  ✅ Завершена: {auth.device_model or 'Unknown'}")
                except Exception as e:
                    print(f"  ❌ Ошибка: {e}")
        if terminated > 0:
            print(f"\n✅ Завершено сессий: {terminated}")
        else:
            print("\n⚠️ Нет других активных сессий")
    except Exception as e:
        print(f"❌ Ошибка при завершении сессий: {e}")

async def menu_check_all_accounts():
    print_header("📊 Проверка всех аккаунтов")
    api_id, api_hash = load_api_credentials()
    tdata_paths = find_tdata_folders()
    session_paths = find_session_files()
    total_accounts = len(tdata_paths) + len(session_paths)
    if total_accounts == 0:
        print("❌ Не найдено ни одного аккаунта!")
        input("\nНажмите Enter для продолжения...")
        return
    print(f"📁 Найдено tdata: {len(tdata_paths)}")
    print(f"📄 Найдено .session: {len(session_paths)}")
    print(f"📊 Всего аккаунтов: {total_accounts}\n")
    valid_accounts = []
    checked = 0
    for tdata_path in tdata_paths:
        checked += 1
        print(f"[{checked}/{total_accounts}]")
        client = await check_session_info(tdata_path, api_id, api_hash)
        if client:
            try:
                me = await client.get_me()
                valid_accounts.append({
                    'folder': Path(tdata_path).parent.name,
                    'name': f"{me.first_name or ''} {me.last_name or ''}".strip(),
                    'username': me.username,
                    'phone': me.phone,
                    'id': me.id,
                    'type': 'tdata'
                })
            except:
                pass
            await client.disconnect()
        if checked < total_accounts:
            await asyncio.sleep(DELAY_BETWEEN_CHECKS)
    for session_path in session_paths:
        checked += 1
        print(f"\n[{checked}/{total_accounts}] 🔍 Проверка session: {session_path}")
        print_separator()
        session_name = str(Path(session_path).with_suffix(''))
        client = TelegramClient(session_name, api_id, api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                print("❌ НЕ АКТИВНА (не авторизована)")
                print_separator()
                continue
            me = await client.get_me()
            print("✅ АКТИВНА")
            print(f"👤 Имя: {me.first_name or ''} {me.last_name or ''}".strip())
            if me.username:
                print(f"📱 Username: @{me.username}")
            else:
                print("📱 Username: не установлен")
            if me.phone:
                print(f"📞 Телефон: +{me.phone}")
            else:
                print("📞 Телефон: скрыт")
            print(f"🆔 ID: {me.id}")
            print_separator()
            valid_accounts.append({
                'folder': Path(session_path).parent.name,
                'name': f"{me.first_name or ''} {me.last_name or ''}".strip(),
                'username': me.username,
                'phone': me.phone,
                'id': me.id,
                'type': 'session'
            })
        except Exception as e:
            print(f"❌ Ошибка: {type(e).__name__}: {e}")
            print_separator()
        finally:
            await client.disconnect()
        if checked < total_accounts:
            await asyncio.sleep(DELAY_BETWEEN_CHECKS)
    if valid_accounts:
        write_valid_accounts(valid_accounts)
        print(f"\n✅ Найдено валидных аккаунтов: {len(valid_accounts)}")
        print(f"📄 Результаты сохранены в: valid.txt")
    else:
        print("\n⚠️ Не найдено ни одного валидного аккаунта")
    print("\n✅ Проверка завершена!")
    input("\nНажмите Enter для продолжения...")

async def menu_check_crypto_wallets():
    print_header("💰 Проверка крипто-кошельков")
    api_id, api_hash = load_api_credentials()
    tdata_paths = find_tdata_folders()
    if not tdata_paths:
        print("❌ Не найдено ни одной папки tdata!")
        input("\nНажмите Enter для продолжения...")
        return
    crypto_bots = load_crypto_bots()
    if not crypto_bots:
        print("❌ Файл crypto_bots.txt не найден или пуст!")
        input("\nНажмите Enter для продолжения...")
        return
    print(f"📁 Найдено папок tdata: {len(tdata_paths)}")
    print(f"🤖 Загружено ботов для проверки: {len(crypto_bots)}\n")
    for i, tdata_path in enumerate(tdata_paths, 1):
        print(f"\n[{i}/{len(tdata_paths)}] Проверка: {tdata_path}")
        print_separator()
        client = None
        try:
            try:
                tdesk = TDesktop(tdata_path)
            except BaseException as e:
                raise_if_control_exception(e)
                print(f"TDA load error: {e}")
                continue
            if not tdesk.isLoaded():
                print("❌ tdata не содержит сессий")
                continue
            client = await tdesk.ToTelethon(session=temporary_session_name(tdata_path), flag=UseCurrentSession, api=API.TelegramIOS.Generate())
            await client.connect()
            if not await client.is_user_authorized():
                print("❌ Сессия не авторизована")
                continue
            me = await client.get_me()
            print(f"👤 Аккаунт: {me.first_name or ''} {me.last_name or ''}".strip())
            if me.username:
                print(f"📱 @{me.username}")
            print(f"\n🔍 Сканирование {len(crypto_bots)} крипто-ботов...")
            start_time = datetime.now()
            active_wallets = await check_crypto_wallets(client)
            end_time = datetime.now()
            scan_duration = (end_time - start_time).total_seconds()
            if active_wallets:
                print(f"\n💼 Найдено активных кошельков: {len(active_wallets)}\n")
                sorted_wallets = sorted(
                    active_wallets.items(),
                    key=lambda x: x[1]['last_message_date'],
                    reverse=True
                )
                for bot_username, info in sorted_wallets:
                    unread_text = f" ({info['unread']} непрочитанных)" if info['unread'] > 0 else ""
                    time_diff = datetime.now(timezone.utc) - info['last_message_date']
                    if time_diff.days > 0:
                        last_activity = f"{time_diff.days} дн. назад"
                    elif time_diff.seconds >= 3600:
                        last_activity = f"{time_diff.seconds // 3600} ч. назад"
                    elif time_diff.seconds >= 60:
                        last_activity = f"{time_diff.seconds // 60} мин. назад"
                    else:
                        last_activity = "только что"
                    print(f"  ✅ @{bot_username}{unread_text}")
                    print(f"     ⏰ Последняя активность: {last_activity}")
            else:
                print("\n⚠️ Активные кошельки не найдены")
            print(f"\n⏱️ Проверка заняла: {scan_duration:.1f} сек")
            print_separator()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
        finally:
            if client:
                await client.disconnect()
        if i < len(tdata_paths):
            await asyncio.sleep(DELAY_BETWEEN_CHECKS)
    print("\n✅ Проверка завершена!")
    input("\nНажмите Enter для продолжения...")

async def menu_terminate_sessions():
    print_header("🔥 Завершение сессий")
    api_id, api_hash = load_api_credentials()
    tdata_paths = find_tdata_folders()
    if not tdata_paths:
        print("❌ Не найдено ни одной папки tdata!")
        input("\nНажмите Enter для продолжения...")
        return
    print(f"📁 Найдено папок tdata: {len(tdata_paths)}\n")
    for i, path in enumerate(tdata_paths, 1):
        print(f"{i}. {path}")
    choice = input("\nВыберите номер аккаунта (или 0 для всех): ").strip()
    try:
        choice_num = int(choice)
        if choice_num == 0:
            selected_paths = tdata_paths
        elif 1 <= choice_num <= len(tdata_paths):
            selected_paths = [tdata_paths[choice_num - 1]]
        else:
            print("❌ Неверный номер!")
            input("\nНажмите Enter для продолжения...")
            return
    except ValueError:
        print("❌ Введите число!")
        input("\nНажмите Enter для продолжения...")
        return
    confirm = input("\n⚠️ Вы уверены? Это завершит все другие сессии! (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y', 'да', 'д']:
        print("❌ Отменено")
        input("\nНажмите Enter для продолжения...")
        return
    for tdata_path in selected_paths:
        print(f"\n🔍 Обработка: {tdata_path}")
        print_separator()
        client = None
        try:
            try:
                tdesk = TDesktop(tdata_path)
            except BaseException as e:
                raise_if_control_exception(e)
                print(f"TDA load error: {e}")
                continue
            if not tdesk.isLoaded():
                print("❌ tdata не содержит сессий")
                continue
            client = await tdesk.ToTelethon(session="session", flag=UseCurrentSession, api=API.TelegramIOS.Generate())
            await client.connect()
            if not await client.is_user_authorized():
                print("❌ Сессия не авторизована")
                continue
            await terminate_other_sessions(client)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
        finally:
            if client:
                await client.disconnect()
    input("\nНажмите Enter для продолжения...")

async def show_menu():
    while True:
        print_header("🔐 Управление Telegram-сессиями")
        print("Выберите действие:\n")
        print("1. 📊 Проверка всех аккаунтов (tdata + session) → valid.txt")
        print("2. 💰 Проверка крипто-кошельков")
        print("3. 🔥 Завершить все сессии (кроме текущей)")
        print("4. 🚪 Выход\n")
        choice = input("Ваш выбор: ").strip()
        if choice == "1":
            await menu_check_all_accounts()
        elif choice == "2":
            await menu_check_crypto_wallets()
        elif choice == "3":
            await menu_terminate_sessions()
        elif choice == "4":
            print("\n👋 До свидания!")
            break
        else:
            print("\n❌ Неверный выбор! Попробуйте снова.\n")

def cleanup_temp_files():
    for temp_file in PROJECT_DIR.glob(".tdata_check_*.session*"):
        try:
            temp_file.unlink()
        except OSError:
            pass

async def main():
    try:
        await show_menu()
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
    finally:
        cleanup_temp_files()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        sys.exit(1)
