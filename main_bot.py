import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import asyncio
from datetime import datetime, timedelta
import os
import re
import time

# Настройки бота
intents = discord.Intents.default()
intents.voice_states = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# КОНФИГУРАЦИЯ
TRIGGER_CHANNEL_IDS = {
    "дуо": 1439645769744519260,
    "сквад": 1439645855756845218,
    "соло": 1439645659882848316,
    "группа": 1439644602847072417,
    "митинг": 1439645198891225210,
    "кино": 1439645357566066818,
}

PLAYER_SEARCH_CHANNEL_ID = 1439646366899896360

VACATION_CONFIG = {
    "request_channel_id": 1439646602104016896,
    "admin_channel_id": 1439646172053635275,
    "vacation_role_id": 1439648201173897357,
}

# Конфигурация верификации
VERIFICATION_CONFIG = {
    "verified_role_id": 1439646749550575636,
    "verification_channel_id": 1439572596361527448,
}

# Шаблоны для временных каналов
CHANNEL_TEMPLATES = {
    "сквад": {"name": "🔹Сквад {}", "user_limit": 4, "category_name": "🔊 Временные каналы"},
    "дуо": {"name": "👥Дуо {}", "user_limit": 2, "category_name": "🔊 Временные каналы"},
    "соло": {"name": "👤Соло {}", "user_limit": 1, "category_name": "🔊 Временные каналы"},
    "группа": {"name": "👾Другие игры {}", "user_limit": 8, "category_name": "🔊 Временные каналы"},
    "митинг": {"name": "🗣️Говорилка {}", "user_limit": 0, "category_name": "🔊 Временные каналы"},
    "кино": {"name": "🎬Кино {}", "user_limit": 0, "category_name": "🔊 Временные каналы"}
}

# Кэши для оптимизации
active_temp_channels = {}
active_searches = {}
active_vacations = {}
verified_players = {}
cooldowns = {}

# ==================== ПРОВЕРКА ПРАВ БОТА ====================

async def check_bot_permissions(guild):
    """Проверяет права бота на сервере"""
    bot_member = guild.get_member(bot.user.id)
    permissions = bot_member.guild_permissions
    
    required_permissions = {
        'manage_roles': permissions.manage_roles,
        'manage_channels': permissions.manage_channels,
        'move_members': permissions.move_members,
        'manage_nicknames': permissions.manage_nicknames,
    }
    
    missing_permissions = [perm for perm, has_perm in required_permissions.items() if not has_perm]
    
    if missing_permissions:
        print(f"⚠️ У бота отсутствуют права: {', '.join(missing_permissions)}")
        return False
    
    print("✅ У бота есть все необходимые права")
    return True

async def safe_add_roles(member, role):
    """Безопасное добавление роли с проверкой прав"""
    try:
        # Проверяем иерархию ролей
        if role.position >= member.guild.me.top_role.position:
            print(f"❌ Роль {role.name} выше роли бота")
            return False
        
        # Проверяем права на управление ролями
        if not member.guild.me.guild_permissions.manage_roles:
            print(f"❌ У бота нет прав на управление ролями")
            return False
        
        await member.add_roles(role)
        print(f"✅ Роль {role.name} выдана пользователю {member.name}")
        return True
        
    except discord.Forbidden:
        print(f"❌ Недостаточно прав для выдачи роли {role.name}")
        return False
    except Exception as e:
        print(f"❌ Ошибка при выдаче роли: {e}")
        return False

async def safe_remove_roles(member, role):
    """Безопасное снятие роли с проверкой прав"""
    try:
        # Проверяем иерархию ролей
        if role.position >= member.guild.me.top_role.position:
            print(f"❌ Роль {role.name} выше роли бота")
            return False
        
        # Проверяем права на управление ролями
        if not member.guild.me.guild_permissions.manage_roles:
            print(f"❌ У бота нет прав на управление ролями")
            return False
        
        await member.remove_roles(role)
        print(f"✅ Роль {role.name} снята с пользователя {member.name}")
        return True
        
    except discord.Forbidden:
        print(f"❌ Недостаточно прав для снятия роли {role.name}")
        return False
    except Exception as e:
        print(f"❌ Ошибка при снятии роли: {e}")
        return False

# ==================== ОПТИМИЗАЦИЯ ПРОИЗВОДИТЕЛЬНОСТИ ====================

def check_cooldown(user_id: int, command: str, cooldown_seconds: int = 3) -> bool:
    """Проверка кд на команды"""
    current_time = time.time()
    key = f"{user_id}_{command}"
    
    if key in cooldowns:
        if current_time - cooldowns[key] < cooldown_seconds:
            return False
    
    cooldowns[key] = current_time
    return True

async def safe_delete_message(message):
    """Безопасное удаление сообщения"""
    try:
        await message.delete()
    except:
        pass

async def safe_send_message(ctx, content=None, embed=None, delete_after=None):
    """Безопасная отправка сообщения с обработкой ошибок"""
    try:
        message = await ctx.send(content=content, embed=embed, delete_after=delete_after)
        return message
    except Exception as e:
        print(f"❌ Ошибка отправки сообщения: {e}")
        return None

# ==================== СИСТЕМА ВЕРИФИКАЦИИ ====================

@bot.command(name='verify')
async def verify_command(ctx, *, verification_text: str = None):
    """Команда для верификации игрока"""
    if not check_cooldown(ctx.author.id, 'verify', 5):
        return
    
    try:
        await safe_delete_message(ctx.message)
        
        if not verification_text:
            embed = discord.Embed(
                title="❌ Неверный формат",
                description="**Использование:** `!verify <никнейм> (<имя>)`\n\n"
                          "**Пример:** `!verify PlayerName (Алексей)`\n\n"
                          "**Правила:**\n"
                          "• Никнейм: только английские буквы, цифры и символы\n"
                          "• Имя в скобках: только русские буквы\n"
                          "• Скобки обязательны!",
                color=0xff0000
            )
            await safe_send_message(ctx, embed=embed, delete_after=30)
            return

        # Проверяем формат: никнейм (имя)
        pattern = r'^([a-zA-Z0-9_\-\.]+)\s+\(([а-яА-ЯёЁ\s]+)\)$'
        match = re.match(pattern, verification_text.strip())
        
        if not match:
            embed = discord.Embed(
                title="❌ Неверный формат",
                description="**Правильный формат:** `никнейм (имя)`\n\n"
                          "**Пример:** `!verify PlayerName (Алексей)`\n\n"
                          "**Ошибки:**\n"
                          "• Используйте английские буквы для ника\n"
                          "• Используйте русские буквы для имени\n"
                          "• Не забудьте скобки вокруг имени",
                color=0xff0000
            )
            await safe_send_message(ctx, embed=embed, delete_after=30)
            return

        pubg_nickname = match.group(1)
        real_name = match.group(2)

        # Дополнительные проверки
        if len(pubg_nickname) < 3 or len(pubg_nickname) > 20:
            embed = discord.Embed(
                title="❌ Ошибка в никнейме",
                description="Никнейм должен быть от 3 до 20 символов",
                color=0xff0000
            )
            await safe_send_message(ctx, embed=embed, delete_after=15)
            return

        if len(real_name) < 2 or len(real_name) > 15:
            embed = discord.Embed(
                title="❌ Ошибка в имени",
                description="Имя должно быть от 2 до 15 символов",
                color=0xff0000
            )
            await safe_send_message(ctx, embed=embed, delete_after=15)
            return

        # Проверяем, не проходил ли пользователь уже верификацию
        if ctx.author.id in verified_players:
            embed = discord.Embed(
                title="❌ Уже верифицирован",
                description="Вы уже прошли верификацию ранее!",
                color=0xff0000
            )
            await safe_send_message(ctx, embed=embed, delete_after=15)
            return

        # Получаем роль верификации
        verified_role = ctx.guild.get_role(VERIFICATION_CONFIG["verified_role_id"])
        if not verified_role:
            embed = discord.Embed(
                title="❌ Ошибка сервера",
                description="Роль верификации не найдена! Обратитесь к администратору.",
                color=0xff0000
            )
            await safe_send_message(ctx, embed=embed, delete_after=15)
            return

        # Создаем новый никнейм
        new_nickname = f"{pubg_nickname} ({real_name})"
        
        # Выдаем роль верификации с проверкой прав
        role_added = await safe_add_roles(ctx.author, verified_role)
        
        if not role_added:
            embed = discord.Embed(
                title="❌ Ошибка прав",
                description="Не удалось выдать роль верификации. Проверьте права бота.",
                color=0xff0000
            )
            await safe_send_message(ctx, embed=embed, delete_after=15)
            return

        # Сохраняем информацию о игроке
        verified_players[ctx.author.id] = {
            'pubg_nickname': pubg_nickname,
            'real_name': real_name,
            'verified_at': datetime.now(),
            'discord_name': ctx.author.name,
            'server_nickname': new_nickname
        }

        # Отправляем сообщение об успехе
        embed = discord.Embed(
            title="✅ Верификация успешна!",
            description=f"**Добро пожаловать, {real_name}!**\n\n"
                      f"**Ваши данные:**\n"
                      f"• 🎮 PUBG ник: `{pubg_nickname}`\n"
                      f"• 👤 Ваше имя: `{real_name}`\n"
                      f"• 📅 Верифицирован: `{datetime.now().strftime('%d.%m.%Y %H:%M')}`\n"
                      f"• 📛 Требуемый ник: `{new_nickname}`\n\n"
                      f"Теперь у вас есть доступ ко всем возможностям сервера! 🎉",
            color=0x00ff00
        )
        
        # Добавляем инструкцию для личных профилей
        embed.add_field(
            name="📝 ВАЖНО: Измените серверный никнейм вручную",
            value=f"**Инструкция для изменения никнейма в личном профиле:**\n\n"
                  f"1. **Нажмите на название сервера** в левом верхнем углу\n"
                  f"2. Выберите **'Профили'** → **'Личные профили сервера'**\n"
                  f"3. Найдите сервер **'{ctx.guild.name}'**\n"
                  f"4. В поле **'Никнейм на сервере'** введите:\n"
                  f"```{new_nickname}```\n"
                  f"5. **Сохраните изменения**\n\n"
                  f"*Это необходимо для идентификации в клане*",
            inline=False
        )
        
        if ctx.author.avatar:
            embed.set_thumbnail(url=ctx.author.avatar.url)
        
        message = await safe_send_message(ctx, embed=embed, delete_after=60)

        # Отправляем дополнительное сообщение в ЛС
        try:
            dm_embed = discord.Embed(
                title=f"📝 Инструкция по изменению ника на сервере {ctx.guild.name}",
                description=f"**Пожалуйста, установите ваш серверный никнейм:**\n```{new_nickname}```\n\n"
                          f"**Как это сделать:**\n"
                          f"1. Нажмите на **название сервера** вверху слева\n"
                          f"2. Выберите **'Профили'** → **'Личные профили сервера'**\n"
                          f"3. Найдите сервер **'{ctx.guild.name}'**\n"
                          f"4. В поле **'Никнейм на сервере'** введите:\n```{new_nickname}```\n"
                          f"5. Нажмите **'Сохранить'**\n\n"
                          f"После этого ваш ник будет отображаться как `{new_nickname}`",
                color=0x3498db
            )
            await ctx.author.send(embed=dm_embed)
        except:
            print(f"⚠️ Не удалось отправить ЛС пользователю {ctx.author.name}")

        # Логируем верификацию
        print(f"✅ Верифицирован: {ctx.author.name} -> {pubg_nickname} ({real_name})")

    except Exception as e:
        print(f"❌ Ошибка в верификации: {e}")
        embed = discord.Embed(
            title="❌ Ошибка",
            description="Произошла ошибка при верификации. Попробуйте позже.",
            color=0xff0000
        )
        await safe_send_message(ctx, embed=embed, delete_after=15)

@bot.command(name='сменить_ник')
async def change_nickname(ctx, *, verification_text: str = None):
    """Команда для смены ника"""
    if not check_cooldown(ctx.author.id, 'change_nickname', 10):
        return
        
    try:
        await safe_delete_message(ctx.message)
        
        if not verification_text:
            embed = discord.Embed(
                title="❌ Неверный формат",
                description="**Использование:** `!сменить_ник <никнейм> (<имя>)`\n\n"
                          "**Пример:** `!сменить_ник NewNickname (НовоеИмя)`",
                color=0xff0000
            )
            await safe_send_message(ctx, embed=embed, delete_after=30)
            return

        # Проверяем, верифицирован ли пользователь
        if ctx.author.id not in verified_players:
            embed = discord.Embed(
                title="❌ Ошибка",
                description="Сначала пройдите верификацию командой `!verify`",
                color=0xff0000
            )
            await safe_send_message(ctx, embed=embed, delete_after=15)
            return

        # Проверяем формат: никнейм (имя)
        pattern = r'^([a-zA-Z0-9_\-\.]+)\s+\(([а-яА-ЯёЁ\s]+)\)$'
        match = re.match(pattern, verification_text.strip())
        
        if not match:
            embed = discord.Embed(
                title="❌ Неверный формат",
                description="**Правильный формат:** `никнейм (имя)`\n\n"
                          "**Пример:** `!сменить_ник NewPlayer (Алексей)`",
                color=0xff0000
            )
            await safe_send_message(ctx, embed=embed, delete_after=30)
            return

        pubg_nickname = match.group(1)
        real_name = match.group(2)

        # Дополнительные проверки
        if len(pubg_nickname) < 3 or len(pubg_nickname) > 20:
            embed = discord.Embed(
                title="❌ Ошибка в никнейме",
                description="Никнейм должен быть от 3 до 20 символов",
                color=0xff0000
            )
            await safe_send_message(ctx, embed=embed, delete_after=15)
            return

        if len(real_name) < 2 or len(real_name) > 15:
            embed = discord.Embed(
                title="❌ Ошибка в имени",
                description="Имя должно быть от 2 до 15 символов",
                color=0xff0000
            )
            await safe_send_message(ctx, embed=embed, delete_after=15)
            return

        # Создаем новый никнейм
        new_nickname = f"{pubg_nickname} ({real_name})"

        # Обновляем информацию о игроке
        verified_players[ctx.author.id] = {
            'pubg_nickname': pubg_nickname,
            'real_name': real_name,
            'verified_at': verified_players[ctx.author.id]['verified_at'],
            'discord_name': ctx.author.name,
            'server_nickname': new_nickname,
            'nickname_updated': datetime.now()
        }

        # Отправляем сообщение об успехе
        embed = discord.Embed(
            title="✅ Данные обновлены!",
            description=f"**Ваши данные обновлены!**\n\n"
                      f"**Новые данные:**\n"
                      f"• 🎮 PUBG ник: `{pubg_nickname}`\n"
                      f"• 👤 Ваше имя: `{real_name}`\n"
                      f"• 📛 Требуемый ник: `{new_nickname}`\n"
                      f"• 📅 Обновлено: `{datetime.now().strftime('%d.%m.%Y %H:%M')}`",
            color=0x00ff00
        )
        
        # Добавляем инструкцию
        embed.add_field(
            name="📝 Инструкция по изменению ника",
            value=f"**Чтобы изменить серверный никнейм:**\n\n"
                  f"1. Нажмите на **название сервера**\n"
                  f"2. Выберите **'Профили'** → **'Личные профили сервера'**\n"
                  f"3. Найдите **'{ctx.guild.name}'**\n"
                  f"4. В поле **'Никнейм на сервере'** введите:\n```{new_nickname}```\n"
                  f"5. **Сохраните изменения**",
            inline=False
        )
        
        if ctx.author.avatar:
            embed.set_thumbnail(url=ctx.author.avatar.url)
        
        await safe_send_message(ctx, embed=embed, delete_after=60)

        print(f"✅ Данные обновлены: {ctx.author.name} -> {pubg_nickname} ({real_name})")

    except Exception as e:
        print(f"❌ Ошибка при смене ника: {e}")
        embed = discord.Embed(
            title="❌ Ошибка",
            description="Произошла ошибка при смене ника. Попробуйте позже.",
            color=0xff0000
        )
        await safe_send_message(ctx, embed=embed, delete_after=15)

# ==================== КОМАНДА ДЛЯ ПОЛУЧЕНИЯ ИНСТРУКЦИИ ====================

@bot.command(name='инструкция')
async def instruction_command(ctx):
    """Команда для получения инструкции по изменению ника"""
    try:
        await safe_delete_message(ctx.message)
    except:
        pass
    
    embed = discord.Embed(
        title="📝 Инструкция по изменению серверного никнейма",
        description="**Как изменить никнейм в личном профиле сервера:**\n\n"
                   "1. **Нажмите на название сервера** в левом верхнем углу\n"
                   "2. Выберите **'Профили'** → **'Личные профили сервера'**\n"
                   "3. Найдите нужный сервер в списке\n"
                   "4. В поле **'Никнейм на сервере'** введите ваш ник\n"
                   "5. **Сохраните изменения**\n\n"
                   "**Формат ника для клана:** `PlayerName (Имя)`\n"
                   "**Пример:** `ProPlayer (Алексей)`",
        color=0x3498db
    )
    
    await safe_send_message(ctx, embed=embed, delete_after=60)

# ==================== СИСТЕМА ОТПУСКОВ (ИСПРАВЛЕННАЯ) ====================

@bot.command(name='отпуск')
async def vacation_command(ctx, duration: str = None):
    """Простая команда для оформления отпуска"""
    if not check_cooldown(ctx.author.id, 'vacation', 10):
        return
        
    try:
        user = ctx.author
        
        if not duration:
            embed = discord.Embed(
                title="🏖️ Система отпусков",
                description="**Использование:** `!отпуск <длительность>`\n\n"
                          "**Доступные варианты:**\n"
                          "• `!отпуск 3д` - 1-3 дня\n"
                          "• `!отпуск неделя` - 7 дней\n" 
                          "• `!отпуск 2недели` - 14 дней\n"
                          "**Для досрочного возвращения:** `!вернулся`",
                color=0x3498db
            )
            await safe_send_message(ctx, embed=embed, delete_after=30)
            return
        
        # Парсим длительность
        duration_lower = duration.lower()
        time_delta = None
        display_duration = ""
        
        if duration_lower in ['3д', '3дня', '3 дня', '3 дня']:
            time_delta = timedelta(days=3)
            display_duration = "1-3 дня"
        elif duration_lower in ['неделя', '7д', '7дней']:
            time_delta = timedelta(weeks=1)
            display_duration = "неделю"
        elif duration_lower in ['2недели', '2 недели', '14д', '14дней']:
            time_delta = timedelta(weeks=2)
            display_duration = "2 недели"
        else:
            await safe_send_message(ctx, "❌ Неверная длительность. Используйте: 3д, неделя, 2недели", delete_after=10)
            return
        
        # Проверяем, не в отпуске ли уже
        vacation_role = ctx.guild.get_role(VACATION_CONFIG["vacation_role_id"])
        if not vacation_role:
            await safe_send_message(ctx, "❌ Роль отпуска не найдена!", delete_after=10)
            return
        
        if vacation_role in user.roles:
            await safe_send_message(ctx, "❌ Вы уже в отпуске!", delete_after=10)
            return
        
        # Выдаем роль с проверкой прав
        role_added = await safe_add_roles(user, vacation_role)
        
        if not role_added:
            embed = discord.Embed(
                title="❌ Ошибка прав",
                description="Не удалось выдать роль отпуска. Проверьте права бота.",
                color=0xff0000
            )
            await safe_send_message(ctx, embed=embed, delete_after=15)
            return
        
        # Отправляем уведомление в админский канал
        admin_channel = ctx.guild.get_channel(VACATION_CONFIG["admin_channel_id"])
        end_date = datetime.now() + time_delta
        
        if admin_channel:
            embed = discord.Embed(
                title="🏖️ Новая заявка на отпуск",
                color=0x00ff00,
                timestamp=datetime.now()
            )
            embed.add_field(name="👤 Сотрудник", value=user.mention, inline=True)
            embed.add_field(name="⏱️ Длительность", value=display_duration, inline=True)
            embed.add_field(name="📅 Дата окончания", value=end_date.strftime("%d.%m.%Y %H:%M"), inline=True)
            
            try:
                admin_message = await admin_channel.send(embed=embed)
                
                # Сохраняем информацию об отпуске
                active_vacations[user.id] = {
                    'end_date': end_date,
                    'admin_message_id': admin_message.id,
                    'duration': display_duration,
                }
            except Exception as e:
                print(f"⚠️ Не удалось отправить сообщение в админский канал: {e}")
        
        # Подтверждаем пользователю
        embed = discord.Embed(
            title="🎉 Заявка на отпуск принята!",
            description=f"**{user.mention}, вы получили роль 🏖️ В отпуске!**\n\n"
                      f"**📅 Период отпуска:** {display_duration}\n"
                      f"**⏰ Дата окончания:** {end_date.strftime('%d.%m.%Y в %H:%M')}\n\n"
                      f"Для досрочного возвращения используйте команду `!вернулся`\n"
                      f"**Хорошего отдыха! 🌴☀️**",
            color=0x00ff00
        )
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        await safe_send_message(ctx, embed=embed)
        
    except Exception as e:
        print(f"❌ Ошибка при обработке заявки на отпуск: {e}")
        embed = discord.Embed(
            title="❌ Ошибка",
            description="Произошла ошибка при оформлении отпуска. Попробуйте позже.",
            color=0xff0000
        )
        await safe_send_message(ctx, embed=embed, delete_after=10)

@bot.command(name='вернулся')
async def back_from_vacation(ctx):
    """Снимает роль отпуска"""
    if not check_cooldown(ctx.author.id, 'back_from_vacation', 5):
        return
        
    try:
        user = ctx.author
        vacation_role = ctx.guild.get_role(VACATION_CONFIG["vacation_role_id"])
        
        if vacation_role and vacation_role in user.roles:
            # Снимаем роль с проверкой прав
            role_removed = await safe_remove_roles(user, vacation_role)
            
            if not role_removed:
                embed = discord.Embed(
                    title="❌ Ошибка прав",
                    description="Не удалось снять роль отпуска. Проверьте права бота.",
                    color=0xff0000
                )
                await safe_send_message(ctx, embed=embed, delete_after=15)
                return
            
            # Удаляем сообщение из админского канала
            if user.id in active_vacations:
                vacation_info = active_vacations[user.id]
                admin_channel = ctx.guild.get_channel(VACATION_CONFIG["admin_channel_id"])
                if admin_channel:
                    try:
                        admin_message = await admin_channel.fetch_message(vacation_info['admin_message_id'])
                        await admin_message.delete()
                    except:
                        pass
                
                del active_vacations[user.id]
            
            embed = discord.Embed(
                title="🎉 Добро пожаловать обратно!",
                description=f"**{user.mention}, рады вашему возвращению!**\n\n"
                          f"Роль **🏖️ В отпуске** была успешно снята.\n"
                          f"Приятной игры! 🎮",
                color=0x00ff00
            )
            await safe_send_message(ctx, embed=embed)
        else:
            await safe_send_message(ctx, "❌ У вас нет роли отпуска.", delete_after=10)
            
    except Exception as e:
        print(f"❌ Ошибка при снятии роли отпуска: {e}")
        embed = discord.Embed(
            title="❌ Ошибка",
            description="Произошла ошибка при снятии роли отпуска. Попробуйте позже.",
            color=0xff0000
        )
        await safe_send_message(ctx, embed=embed, delete_after=10)

# ==================== СИСТЕМА ПОИСКА ИГРОКОВ (УЛУЧШЕННАЯ) ====================

class PlayerSearchView(View):
    def __init__(self, voice_channel, search_text, author, message):
        super().__init__(timeout=3600)
        self.voice_channel = voice_channel
        self.search_text = search_text
        self.author = author
        self.message = message
        self.joined_users = set()
        self.last_update = datetime.now()

    @discord.ui.button(label="🎮 Присоединиться", style=discord.ButtonStyle.success)
    async def join_search(self, interaction: discord.Interaction, button: Button):
        try:
            user = interaction.user
            
            if user.id == self.author.id:
                await interaction.response.send_message("❌ Вы не можете присоединиться к своему поиску!", ephemeral=True)
                return
            
            if user.id in self.joined_users:
                await interaction.response.send_message("❌ Вы уже присоединились!", ephemeral=True)
                return
            
            if not self.voice_channel:
                await interaction.response.send_message("❌ Канал не найден!", ephemeral=True)
                return
            
            self.joined_users.add(user.id)
            self.last_update = datetime.now()
            
            # Обновляем сообщение
            await self.update_message()
            await interaction.response.defer()
                    
        except Exception as e:
            print(f"❌ Ошибка в join_search: {e}")

    @discord.ui.button(label="🚪 Покинуть", style=discord.ButtonStyle.danger)
    async def leave_search(self, interaction: discord.Interaction, button: Button):
        try:
            user = interaction.user
            
            if user.id not in self.joined_users:
                await interaction.response.send_message("❌ Вы не присоединялись!", ephemeral=True)
                return
            
            self.joined_users.remove(user.id)
            self.last_update = datetime.now()
            
            await self.update_message()
            await interaction.response.defer()
            
        except Exception as e:
            print(f"❌ Ошибка в leave_search: {e}")

    @discord.ui.button(label="❌ Завершить", style=discord.ButtonStyle.secondary)
    async def cancel_search(self, interaction: discord.Interaction, button: Button):
        try:
            user = interaction.user
            
            if user.id != self.author.id:
                await interaction.response.send_message("❌ Только автор может завершить поиск!", ephemeral=True)
                return
            
            await self.remove_search()
            await interaction.response.defer()
                
        except Exception as e:
            print(f"❌ Ошибка в cancel_search: {e}")

    async def update_message(self):
        """Обновляет сообщение поиска"""
        try:
            embed = await self.create_embed()
            await self.message.edit(embed=embed, view=self)
        except Exception as e:
            print(f"❌ Ошибка при обновлении сообщения поиска: {e}")

    async def create_embed(self):
        """Создает красивый embed для поиска с информацией о канале"""
        current_players = len(self.voice_channel.members) if self.voice_channel else 0
        max_players = self.voice_channel.user_limit if self.voice_channel and self.voice_channel.user_limit > 0 else "∞"
        
        embed = discord.Embed(
            title="🎯 ПОИСК ИГРОКОВ",
            description=f"**{self.author.mention} ищет команду!**\n\n"
                       f"**📝 Описание поиска:**\n{self.search_text}",
            color=0x3498db,
            timestamp=self.last_update
        )
        
        # Статус канала
        embed.add_field(
            name="🔊 ГОЛОСОВОЙ КАНАЛ",
            value=f"**➥ {self.voice_channel.mention if self.voice_channel else '❌ Канал удален'}**\n"
                  f"👥 **Игроков:** {current_players}/{max_players}",
            inline=False
        )
        
        # Список игроков в канале
        if self.voice_channel and self.voice_channel.members:
            members = self.voice_channel.members
            members_list = "\n".join([f"• {member.mention}" for member in members[:8]])
            if len(members) > 8:
                members_list += f"\n• ... и еще {len(members) - 8} игроков"
            
            embed.add_field(
                name=f"👥 В КАНАЛЕ ({len(members)})",
                value=members_list,
                inline=True
            )
        else:
            embed.add_field(
                name="👥 В КАНАЛЕ",
                value="*Канал пуст*",
                inline=True
            )
        
        # Список присоединившихся к поиску
        if self.joined_users:
            joined_list = []
            for user_id in list(self.joined_users)[:6]:
                user = self.voice_channel.guild.get_member(user_id) if self.voice_channel else None
                if user:
                    joined_list.append(f"• {user.mention}")
            
            if len(self.joined_users) > 6:
                joined_list.append(f"• ... и еще {len(self.joined_users) - 6}")
            
            embed.add_field(
                name=f"🎮 ОТКЛИКНУЛИСЬ ({len(self.joined_users)})",
                value="\n".join(joined_list) if joined_list else "*Пока никто*",
                inline=True
            )
        else:
            embed.add_field(
                name="🎮 ОТКЛИКНУЛИСЬ",
                value="*Пока никто*",
                inline=True
            )
        
        embed.set_footer(text="Заходи быстрее💀")
        if self.author.avatar:
            embed.set_thumbnail(url=self.author.avatar.url)
        
        return embed

    async def remove_search(self):
        """Удаляет поиск"""
        try:
            await self.message.delete()
        except:
            pass
        finally:
            if self.author.id in active_searches:
                del active_searches[self.author.id]

async def remove_search(user_id):
    """Удаляет поиск по ID пользователя"""
    if user_id in active_searches:
        search_view = active_searches[user_id]
        await search_view.remove_search()

@tasks.loop(seconds=30)
async def update_searches_task():
    """Задача для автоматического обновления поисков"""
    await check_active_searches()

async def check_active_searches():
    """Проверяет все активные поиски и удаляет неактуальные"""
    current_time = datetime.now()
    
    for user_id, search_view in list(active_searches.items()):
        try:
            # Проверяем существует ли еще канал
            if not search_view.voice_channel:
                await search_view.remove_search()
                continue
                
            # Проверяем находится ли автор еще в канале
            author_in_channel = any(member.id == user_id for member in search_view.voice_channel.members)
            
            if not author_in_channel:
                await search_view.remove_search()
                continue
                
            # Обновляем сообщение с актуальной информацией
            await search_view.update_message()
                
        except Exception as e:
            print(f"❌ Ошибка при проверке поиска: {e}")
            await search_view.remove_search()

@bot.command(name='i')
async def player_search(ctx, *, search_text: str = "Ищем игроков!"):
    """Создает объявление о поиске игроков с полной информацией"""
    if not check_cooldown(ctx.author.id, 'player_search', 10):
        return
        
    try:
        await safe_delete_message(ctx.message)
    except:
        pass
    
    if ctx.author.id in active_searches:
        embed = discord.Embed(
            title="❌ Ошибка",
            description="У вас уже есть активный поиск! Завершите его перед созданием нового.",
            color=0xff0000
        )
        await safe_send_message(ctx, embed=embed, delete_after=10)
        return
    
    if not ctx.author.voice:
        embed = discord.Embed(
            title="❌ Ошибка",
            description="Вы должны находиться в голосовом канале для создания поиска!",
            color=0xff0000
        )
        await safe_send_message(ctx, embed=embed, delete_after=10)
        return
    
    voice_channel = ctx.author.voice.channel
    
    # Создаем временное сообщение
    temp_embed = discord.Embed(
        title="🎯 Создание поиска...",
        description="Инициализация системы поиска игроков",
        color=0x3498db
    )
    
    temp_message = await safe_send_message(ctx, embed=temp_embed)
    if not temp_message:
        return
    
    # Создаем view и обновляем сообщение
    view = PlayerSearchView(voice_channel, search_text, ctx.author, temp_message)
    embed = await view.create_embed()
    
    await temp_message.edit(embed=embed, view=view)
    active_searches[ctx.author.id] = view

@bot.command(name='поиск')
async def player_search_ru(ctx, *, search_text: str = "Ищем игроков!"):
    """Альтернативная команда для поиска игроков"""
    await player_search(ctx, search_text=search_text)

# ==================== СИСТЕМА ВРЕМЕННЫХ КАНАЛОВ ====================

@bot.event
async def on_voice_state_update(member, before, after):
    """Создание временных каналов по триггеру"""
    try:
        if after.channel and after.channel.id in TRIGGER_CHANNEL_IDS.values():
            channel_type = None
            for type_name, channel_id in TRIGGER_CHANNEL_IDS.items():
                if channel_id == after.channel.id:
                    channel_type = type_name
                    break
            
            if channel_type and channel_type in CHANNEL_TEMPLATES:
                await create_temp_channel(member, channel_type)
        
        if before.channel:
            if member.id in active_searches:
                await remove_search(member.id)
            
            if before.channel.id in active_temp_channels and len(before.channel.members) == 0:
                await asyncio.sleep(10)
                if len(before.channel.members) == 0:
                    try:
                        await before.channel.delete()
                        del active_temp_channels[before.channel.id]
                    except:
                        pass
    except Exception as e:
        print(f"❌ Ошибка в on_voice_state_update: {e}")

async def create_temp_channel(member, channel_type):
    """Создает временный канал"""
    try:
        template = CHANNEL_TEMPLATES[channel_type]
        guild = member.guild
        
        category = None
        for cat in guild.categories:
            if cat.name == template["category_name"]:
                category = cat
                break
        
        if not category:
            category = await guild.create_category(template["category_name"])
        
        channel_number = len([c for c in guild.voice_channels if c.name.startswith(template["name"].split(" ")[0])]) + 1
        channel_name = template["name"].format(channel_number)
        
        new_channel = await guild.create_voice_channel(
            name=channel_name,
            user_limit=template["user_limit"],
            category=category
        )
        
        await member.move_to(new_channel)
        active_temp_channels[new_channel.id] = {
            'type': channel_type,
            'created_by': member.id,
            'created_at': datetime.now()
        }
        
        print(f"✅ Создан временный канал: {channel_name}")
        
    except Exception as e:
        print(f"❌ Ошибка создания временного канала: {e}")

# ==================== ОСТАЛЬНЫЕ КОМАНДЫ ====================

@bot.command(name='верификация')
async def verification_help(ctx):
    """Помощь по верификации"""
    try:
        await safe_delete_message(ctx.message)
    except:
        pass
    
    embed = discord.Embed(
        title="🔐 ВЕРИФИКАЦИЯ ИГРОКА",
        description="**Для доступа к серверу необходимо пройти верификацию!**\n\n"
                   "**Команда:** `!verify <никнейм> (<имя>)`\n\n"
                   "**Примеры:**\n"
                   "• `!verify ProPlayer (Алексей)`\n"
                   "• `!verify SniperWolf (Мария)`\n"
                   "• `!verify Top_Fragger (Иван)`\n\n"
                   "**Правила:**\n"
                   "• Никнейм: английские буквы, цифры, символы _-.\n"
                   "• Имя: только русские буквы в скобках\n"
                   "• Скобки вокруг имени обязательны!\n\n"
                   "**После верификации:**\n"
                   "• Вы получите специальную роль\n"
                   "• Получите подробную инструкцию по изменению ника\n"
                   "• Откроется доступ ко всем разделам сервера",
        color=0x3498db
    )
    
    await safe_send_message(ctx, embed=embed, delete_after=60)

@bot.command(name='проверить')
async def check_verification(ctx, member: discord.Member = None):
    """Проверяет статус верификации"""
    if not check_cooldown(ctx.author.id, 'check_verification', 5):
        return
        
    try:
        await safe_delete_message(ctx.message)
    except:
        pass
    
    target_member = member or ctx.author
    player_info = verified_players.get(target_member.id)
    
    if player_info:
        embed = discord.Embed(
            title=f"✅ {target_member.display_name} верифицирован",
            description=f"**Данные игрока:**\n"
                       f"• 🎮 PUBG ник: `{player_info['pubg_nickname']}`\n"
                       f"• 👤 Реальное имя: `{player_info['real_name']}`\n"
                       f"• 📅 Дата верификации: `{player_info['verified_at'].strftime('%d.%m.%Y %H:%M')}`\n"
                       f"• 📛 Требуемый ник: `{player_info['server_nickname']}`",
            color=0x00ff00
        )
        
        embed.add_field(
            name="📝 Инструкция",
            value=f"Используйте `!инструкция` для получения инструкции по изменению ника",
            inline=False
        )
    else:
        embed = discord.Embed(
            title=f"❌ {target_member.display_name} не верифицирован",
            description="Игрок еще не прошел верификацию.\n"
                       "Используйте команду `!верификация` для инструкций.",
            color=0xff0000
        )
    
    await safe_send_message(ctx, embed=embed, delete_after=30)

# ==================== ЗАПУСК БОТА ====================

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')
    print('🎯 Доступные команды: !verify, !верификация, !проверить, !сменить_ник, !инструкция, !отпуск, !вернулся, !i, !поиск')
    
    # Проверяем права бота на всех серверах
    for guild in bot.guilds:
        await check_bot_permissions(guild)
    
    if not update_searches_task.is_running():
        update_searches_task.start()

@bot.event
async def on_command_error(ctx, error):
    """Обработка ошибок команд"""
    if isinstance(error, commands.CommandNotFound):
        return
    
    print(f"❌ Ошибка команды: {error}")

# Запуск бота
if __name__ == "__main__":
    print("🚀 Запуск бота...")
    token = os.getenv('DISCORD_BOT_TOKEN', 'MTQzOTM2NjQ5NDYyNTQ2NDUyMQ.GgB7d9.j6MVEst9Rg4Qps5PUf8Bg29Mmh6v8vJ8s_C23A')
    bot.run(token)