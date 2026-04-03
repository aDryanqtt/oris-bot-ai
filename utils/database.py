"""
Banco de Dados SQLite — Sistema robusto com transações atômicas.
Usa aiosqlite para operações assíncronas.
Todas as operações de economia usam transações para evitar bugs de saldo.
"""

import aiosqlite
import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'oris.db')


class Database:
    """Gerenciador de banco de dados SQLite assíncrono."""

    def __init__(self):
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self):
        """Conecta ao banco e cria tabelas."""
        # Garante que o diretório data/ existe
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

        self._db = await aiosqlite.connect(DB_PATH)
        self._db.row_factory = aiosqlite.Row

        # WAL mode para melhor concorrência
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.execute("PRAGMA busy_timeout=5000")

        await self._create_tables()
        logger.info(f"✅ Banco de dados conectado: {DB_PATH}")

    async def close(self):
        """Fecha a conexão."""
        if self._db:
            await self._db.close()
            logger.info("🔒 Banco de dados fechado.")

    async def _create_tables(self):
        """Cria todas as tabelas necessárias."""
        await self._db.executescript("""
            -- Perfil de usuários
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL DEFAULT 'Desconhecido',
                total_messages INTEGER DEFAULT 0,
                total_commands INTEGER DEFAULT 0,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                persona TEXT DEFAULT 'padrao',
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );

            -- Sistema de economia (tabela separada para transações atômicas)
            CREATE TABLE IF NOT EXISTS economy (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 0 CHECK(balance >= 0),
                total_earned INTEGER DEFAULT 0,
                total_spent INTEGER DEFAULT 0,
                daily_streak INTEGER DEFAULT 0,
                last_daily TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            -- Log de transações econômicas (auditoria)
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            -- Patch: Força recriação da tabela para aplicar channel_id e isolar memória
            DROP TABLE IF EXISTS conversations;

            -- Histórico de conversas persistente
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL DEFAULT 0,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            -- Lembretes
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER,
                message TEXT NOT NULL,
                remind_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            -- Log de comandos
            CREATE TABLE IF NOT EXISTS command_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER,
                channel_id INTEGER,
                command_name TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            -- Avisos de moderação
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            -- Canais ignorados pela IA (Hand-off para Humanos)
            CREATE TABLE IF NOT EXISTS ignored_channels (
                channel_id INTEGER PRIMARY KEY
            );

            -- Configurações do servidor
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                bot_channel_id INTEGER
            );

            -- Configurações globais do bot
            CREATE TABLE IF NOT EXISTS bot_config (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            -- Canais monitorados para base de conhecimento da IA
            CREATE TABLE IF NOT EXISTS scan_channels (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                label TEXT,
                added_at TEXT NOT NULL
            );

            -- Índices para performance
            CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
            CREATE INDEX IF NOT EXISTS idx_conversations_user_channel ON conversations(user_id, channel_id);
            CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp);
            CREATE INDEX IF NOT EXISTS idx_reminders_remind_at ON reminders(remind_at);
            CREATE INDEX IF NOT EXISTS idx_reminders_completed ON reminders(completed);
            CREATE INDEX IF NOT EXISTS idx_command_logs_user ON command_logs(user_id);
            CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
        """)
        await self._db.commit()

    # ==================== USUÁRIOS ====================

    async def _ensure_user(self, user_id: int, username: str = "Desconhecido"):
        """Garante que o usuário existe no DB. USO INTERNO — NÃO adquire lock."""
        from config import now_br
        now = now_br().isoformat()

        cursor = await self._db.execute(
            "SELECT user_id FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()

        if row:
            await self._db.execute(
                "UPDATE users SET last_seen = ?, username = ? WHERE user_id = ?",
                (now, username, user_id)
            )
        else:
            await self._db.execute(
                """INSERT INTO users (user_id, username, first_seen, last_seen)
                   VALUES (?, ?, ?, ?)""",
                (user_id, username, now, now)
            )
            await self._db.execute(
                "INSERT OR IGNORE INTO economy (user_id, balance) VALUES (?, 0)",
                (user_id,)
            )

    async def get_or_create_user(self, user_id: int, username: str = "Desconhecido") -> dict:
        """Busca ou cria um usuário. Sempre retorna um dict."""
        async with self._lock:
            await self._ensure_user(user_id, username)
            await self._db.commit()

            cursor = await self._db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            return dict(row)

    async def increment_messages(self, user_id: int, username: str = "Desconhecido"):
        """Incrementa contador de mensagens e dá XP."""
        import random
        xp_gain = random.randint(10, 25)

        async with self._lock:
            await self._ensure_user(user_id, username)
            await self._db.execute(
                """UPDATE users SET
                    total_messages = total_messages + 1,
                    xp = xp + ?,
                    last_seen = ?
                   WHERE user_id = ?""",
                (xp_gain, datetime.now().isoformat(), user_id)
            )
            # Verifica level up
            cursor = await self._db.execute(
                "SELECT xp, level FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            new_level = row['level'] if row else 1
            if row:
                xp, level = row['xp'], row['level']
                next_level_xp = level * 100
                new_level = level
                while xp >= next_level_xp:
                    xp -= next_level_xp
                    new_level += 1
                    next_level_xp = new_level * 100

                if new_level != level:
                    await self._db.execute(
                        "UPDATE users SET level = ?, xp = ? WHERE user_id = ?",
                        (new_level, xp, user_id)
                    )

            await self._db.commit()
            return xp_gain, row['level'] if row else 1, new_level

    async def increment_commands(self, user_id: int, command_name: str, guild_id: int = None, channel_id: int = None):
        """Registra uso de comando."""
        async with self._lock:
            from config import now_br
            now = now_br().isoformat()

            await self._db.execute(
                "UPDATE users SET total_commands = total_commands + 1 WHERE user_id = ?",
                (user_id,)
            )
            await self._db.execute(
                """INSERT INTO command_logs (user_id, guild_id, channel_id, command_name, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, guild_id, channel_id, command_name, now)
            )
            await self._db.commit()

    async def get_user_persona(self, user_id: int) -> str:
        """Retorna a persona salva do usuário."""
        cursor = await self._db.execute(
            "SELECT persona FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row['persona'] if row else 'padrao'

    async def set_user_persona(self, user_id: int, persona: str):
        """Salva a persona do usuário."""
        async with self._lock:
            await self._db.execute(
                "UPDATE users SET persona = ? WHERE user_id = ?",
                (persona, user_id)
            )
            await self._db.commit()

    async def get_top_users(self, guild_members: list[int], limit: int = 10) -> list:
        """Retorna top usuários por XP de um servidor."""
        if not guild_members:
            return []
        placeholders = ','.join('?' * len(guild_members))
        cursor = await self._db.execute(
            f"""SELECT user_id, username, xp, level, total_messages
                FROM users
                WHERE user_id IN ({placeholders})
                ORDER BY level DESC, xp DESC
                LIMIT ?""",
            (*guild_members, limit)
        )
        return [dict(row) for row in await cursor.fetchall()]

    # ==================== ECONOMIA (TRANSAÇÕES ATÔMICAS) ====================

    async def get_balance(self, user_id: int) -> int:
        """Retorna saldo do usuário."""
        cursor = await self._db.execute(
            "SELECT balance FROM economy WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row['balance'] if row else 0

    async def get_economy_profile(self, user_id: int) -> dict:
        """Retorna perfil econômico completo."""
        cursor = await self._db.execute(
            "SELECT * FROM economy WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return {'user_id': user_id, 'balance': 0, 'total_earned': 0,
                'total_spent': 0, 'daily_streak': 0, 'last_daily': None}

    async def add_coins(self, user_id: int, amount: int, description: str = "Sistema") -> tuple[bool, int]:
        """
        Adiciona moedas ao saldo. TRANSAÇÃO ATÔMICA.
        Retorna: (sucesso, novo_saldo)
        """
        if amount <= 0:
            return False, 0

        async with self._lock:
            try:
                from config import now_br
                now = now_br().isoformat()

                # Garante que o usuário existe na tabela economy
                cursor = await self._db.execute(
                    "SELECT balance FROM economy WHERE user_id = ?", (user_id,)
                )
                row = await cursor.fetchone()

                if not row:
                    await self._db.execute(
                        "INSERT INTO economy (user_id, balance) VALUES (?, 0)",
                        (user_id,)
                    )
                    current_balance = 0
                else:
                    current_balance = row['balance']

                new_balance = current_balance + amount

                await self._db.execute(
                    """UPDATE economy SET
                        balance = ?,
                        total_earned = total_earned + ?
                       WHERE user_id = ?""",
                    (new_balance, amount, user_id)
                )

                # Registra transação
                await self._db.execute(
                    """INSERT INTO transactions (user_id, amount, balance_after, type, description, timestamp)
                       VALUES (?, ?, ?, 'credit', ?, ?)""",
                    (user_id, amount, new_balance, description, now)
                )

                await self._db.commit()
                return True, new_balance

            except Exception as e:
                await self._db.rollback()
                logger.error(f"Erro ao adicionar moedas: {e}")
                return False, 0

    async def remove_coins(self, user_id: int, amount: int, description: str = "Sistema") -> tuple[bool, int]:
        """
        Remove moedas do saldo. TRANSAÇÃO ATÔMICA.
        Falha se o saldo for insuficiente (CHECK constraint + validação).
        Retorna: (sucesso, novo_saldo)
        """
        if amount <= 0:
            return False, 0

        async with self._lock:
            try:
                from config import now_br
                now = now_br().isoformat()

                # Verifica saldo DENTRO da transação
                cursor = await self._db.execute(
                    "SELECT balance FROM economy WHERE user_id = ?", (user_id,)
                )
                row = await cursor.fetchone()

                if not row or row['balance'] < amount:
                    return False, row['balance'] if row else 0

                new_balance = row['balance'] - amount

                await self._db.execute(
                    """UPDATE economy SET
                        balance = ?,
                        total_spent = total_spent + ?
                       WHERE user_id = ?""",
                    (new_balance, amount, user_id)
                )

                # Registra transação
                await self._db.execute(
                    """INSERT INTO transactions (user_id, amount, balance_after, type, description, timestamp)
                       VALUES (?, ?, ?, 'debit', ?, ?)""",
                    (user_id, -amount, new_balance, description, now)
                )

                await self._db.commit()
                return True, new_balance

            except Exception as e:
                await self._db.rollback()
                logger.error(f"Erro ao remover moedas: {e}")
                return False, 0

    async def transfer_coins(self, from_id: int, to_id: int, amount: int) -> tuple[bool, str]:
        """
        Transferência atômica entre dois usuários.
        Verifica saldo, debita de um, credita no outro — tudo numa transação.
        Retorna: (sucesso, mensagem)
        """
        if amount <= 0:
            return False, "O valor precisa ser positivo."
        if from_id == to_id:
            return False, "Você não pode transferir pra si mesmo!"

        async with self._lock:
            try:
                from config import now_br
                now = now_br().isoformat()

                # Verifica saldo do remetente
                cursor = await self._db.execute(
                    "SELECT balance FROM economy WHERE user_id = ?", (from_id,)
                )
                row = await cursor.fetchone()
                if not row or row['balance'] < amount:
                    return False, f"Saldo insuficiente! Você tem **{row['balance'] if row else 0} OC**."

                sender_new = row['balance'] - amount

                # Verifica se o destinatário existe
                cursor = await self._db.execute(
                    "SELECT balance FROM economy WHERE user_id = ?", (to_id,)
                )
                row_to = await cursor.fetchone()
                if not row_to:
                    # Cria entrada de economia pro destinatário
                    await self._db.execute(
                        "INSERT OR IGNORE INTO economy (user_id, balance) VALUES (?, 0)",
                        (to_id,)
                    )
                    receiver_new = amount
                else:
                    receiver_new = row_to['balance'] + amount

                # Debita remetente
                await self._db.execute(
                    """UPDATE economy SET
                        balance = ?,
                        total_spent = total_spent + ?
                       WHERE user_id = ?""",
                    (sender_new, amount, from_id)
                )

                # Credita destinatário
                await self._db.execute(
                    """UPDATE economy SET
                        balance = ?,
                        total_earned = total_earned + ?
                       WHERE user_id = ?""",
                    (receiver_new, amount, to_id)
                )

                # Log das transações
                await self._db.execute(
                    """INSERT INTO transactions (user_id, amount, balance_after, type, description, timestamp)
                       VALUES (?, ?, ?, 'transfer_out', ?, ?)""",
                    (from_id, -amount, sender_new, f"Transferência para {to_id}", now)
                )
                await self._db.execute(
                    """INSERT INTO transactions (user_id, amount, balance_after, type, description, timestamp)
                       VALUES (?, ?, ?, 'transfer_in', ?, ?)""",
                    (to_id, amount, receiver_new, f"Transferência de {from_id}", now)
                )

                await self._db.commit()
                return True, f"Transferência de **{amount} OC** realizada com sucesso!"

            except Exception as e:
                await self._db.rollback()
                logger.error(f"Erro na transferência: {e}")
                return False, f"Erro na transferência: {str(e)}"

    async def claim_daily(self, user_id: int) -> tuple[bool, int, int, str]:
        """
        Resgata recompensa diária.
        Retorna: (sucesso, valor_ganho, streak, mensagem_erro)
        """
        async with self._lock:
            try:
                from config import now_br
                now = now_br()
                today_str = now.strftime("%Y-%m-%d")

                cursor = await self._db.execute(
                    "SELECT * FROM economy WHERE user_id = ?", (user_id,)
                )
                row = await cursor.fetchone()

                if not row:
                    await self._db.execute(
                        "INSERT INTO economy (user_id, balance) VALUES (?, 0)",
                        (user_id,)
                    )
                    last_daily = None
                    streak = 0
                    balance = 0
                else:
                    last_daily = row['last_daily']
                    streak = row['daily_streak']
                    balance = row['balance']

                # Verifica se já resgatou hoje
                if last_daily and last_daily == today_str:
                    return False, 0, streak, "Você já resgatou seu daily hoje! Volte amanhã. ⏰"

                # Verifica streak
                if last_daily:
                    from datetime import datetime as dt, timedelta
                    last_date = dt.strptime(last_daily, "%Y-%m-%d").date()
                    today = now.date()
                    diff = (today - last_date).days

                    if diff == 1:
                        streak += 1  # Streak mantido
                    elif diff > 1:
                        streak = 1  # Streak quebrado
                else:
                    streak = 1  # Primeiro daily

                # Calcula recompensa: 100 base + 25 por dia de streak (max 500 bonus)
                bonus = min(streak * 25, 500)
                reward = 100 + bonus
                new_balance = balance + reward

                await self._db.execute(
                    """UPDATE economy SET
                        balance = ?,
                        total_earned = total_earned + ?,
                        daily_streak = ?,
                        last_daily = ?
                       WHERE user_id = ?""",
                    (new_balance, reward, streak, today_str, user_id)
                )

                # Log da transação
                await self._db.execute(
                    """INSERT INTO transactions (user_id, amount, balance_after, type, description, timestamp)
                       VALUES (?, ?, ?, 'daily', ?, ?)""",
                    (user_id, reward, new_balance, f"Daily reward (streak {streak})", now.isoformat())
                )

                await self._db.commit()
                return True, reward, streak, ""

            except Exception as e:
                await self._db.rollback()
                logger.error(f"Erro no daily: {e}")
                return False, 0, 0, f"Erro ao resgatar daily: {str(e)}"

    async def get_top_economy(self, guild_members: list[int], limit: int = 10) -> list:
        """Top usuários por saldo."""
        if not guild_members:
            return []
        placeholders = ','.join('?' * len(guild_members))
        cursor = await self._db.execute(
            f"""SELECT e.user_id, e.balance, e.daily_streak, u.username
                FROM economy e
                JOIN users u ON e.user_id = u.user_id
                WHERE e.user_id IN ({placeholders})
                ORDER BY e.balance DESC
                LIMIT ?""",
            (*guild_members, limit)
        )
        return [dict(row) for row in await cursor.fetchall()]

    # ==================== CONVERSAS ====================

    async def save_message(self, user_id: int, channel_id: int, role: str, content: str):
        """Salva uma mensagem no histórico vinculada a um canal para evitar vazamento."""
        async with self._lock:
            from config import now_br
            await self._db.execute(
                """INSERT INTO conversations (user_id, channel_id, role, content, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, channel_id, role, content[:4000], now_br().isoformat())
            )
            await self._db.commit()

    async def get_conversation_history(self, user_id: int, channel_id: int, limit: int = 30) -> list:
        """Retorna últimas N mensagens do usuário num canal de forma isolada."""
        cursor = await self._db.execute(
            """SELECT role, content FROM conversations
               WHERE user_id = ? AND channel_id = ?
               ORDER BY id DESC LIMIT ?""",
            (user_id, channel_id, limit)
        )
        rows = await cursor.fetchall()
        # Inverte pra ter ordem cronológica
        return [{"role": row['role'], "content": row['content']} for row in reversed(rows)]

    async def clear_conversation(self, user_id: int, channel_id: int):
        """Limpa histórico de conversas."""
        async with self._lock:
            await self._db.execute(
                "DELETE FROM conversations WHERE user_id = ? AND channel_id = ?",
                (user_id, channel_id)
            )
            await self._db.commit()

    # ==================== LEMBRETES ====================

    async def create_reminder(self, user_id: int, channel_id: int, guild_id: int,
                              message: str, remind_at: str) -> int:
        """Cria um lembrete. Retorna o ID."""
        async with self._lock:
            from config import now_br
            cursor = await self._db.execute(
                """INSERT INTO reminders (user_id, channel_id, guild_id, message, remind_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, channel_id, guild_id, message, remind_at, now_br().isoformat())
            )
            await self._db.commit()
            return cursor.lastrowid

    async def get_pending_reminders(self) -> list:
        """Retorna lembretes pendentes que já passaram da hora."""
        from config import now_br
        cursor = await self._db.execute(
            """SELECT * FROM reminders
               WHERE completed = 0 AND remind_at <= ?
               ORDER BY remind_at""",
            (now_br().isoformat(),)
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def complete_reminder(self, reminder_id: int):
        """Marca lembrete como completo."""
        async with self._lock:
            await self._db.execute(
                "UPDATE reminders SET completed = 1 WHERE id = ?",
                (reminder_id,)
            )
            await self._db.commit()

    async def get_user_reminders(self, user_id: int) -> list:
        """Lista lembretes ativos do usuário."""
        cursor = await self._db.execute(
            """SELECT * FROM reminders
               WHERE user_id = ? AND completed = 0
               ORDER BY remind_at""",
            (user_id,)
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def cancel_reminder(self, reminder_id: int, user_id: int) -> bool:
        """Cancela um lembrete (verifica ownership)."""
        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM reminders WHERE id = ? AND user_id = ? AND completed = 0",
                (reminder_id, user_id)
            )
            await self._db.commit()
            return cursor.rowcount > 0

    # ==================== MODERAÇÃO ====================

    async def add_warning(self, user_id: int, guild_id: int, moderator_id: int, reason: str) -> int:
        """Adiciona aviso a um usuário."""
        async with self._lock:
            from config import now_br
            cursor = await self._db.execute(
                """INSERT INTO warnings (user_id, guild_id, moderator_id, reason, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, guild_id, moderator_id, reason, now_br().isoformat())
            )
            await self._db.commit()
            return cursor.lastrowid

    async def get_warnings(self, user_id: int, guild_id: int) -> list:
        """Lista avisos de um usuário no servidor."""
        cursor = await self._db.execute(
            """SELECT * FROM warnings
               WHERE user_id = ? AND guild_id = ?
               ORDER BY timestamp DESC""",
            (user_id, guild_id)
        )
        return [dict(row) for row in await cursor.fetchall()]

    # ==================== ESTATÍSTICAS ====================

    async def get_bot_stats(self) -> dict:
        """Estatísticas globais do bot."""
        stats = {}
        cursor = await self._db.execute("SELECT COUNT(*) as c FROM users")
        row = await cursor.fetchone()
        stats['total_users'] = row['c']

        cursor = await self._db.execute("SELECT COUNT(*) as c FROM command_logs")
        row = await cursor.fetchone()
        stats['total_commands'] = row['c']

        cursor = await self._db.execute("SELECT SUM(total_messages) as c FROM users")
        row = await cursor.fetchone()
        stats['total_messages'] = row['c'] or 0

        cursor = await self._db.execute("SELECT COUNT(*) as c FROM conversations")
        row = await cursor.fetchone()
        stats['total_conversations'] = row['c']

        return stats


    async def get_bot_config(self, key: str) -> str | None:
        """Busca configuração global do bot."""
        cursor = await self._db.execute(
            "SELECT value FROM bot_config WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row['value'] if row else None

    async def set_bot_config(self, key: str, value: str | None):
        """Define ou apaga configuração global."""
        async with self._lock:
            if value is None:
                await self._db.execute("DELETE FROM bot_config WHERE key = ?", (key,))
            else:
                await self._db.execute(
                    """INSERT INTO bot_config (key, value) VALUES (?, ?)
                       ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                    (key, str(value))
                )
            await self._db.commit()

    async def get_bot_channel(self, guild_id: int) -> int | None:
        """Retorna o ID do canal exclusivo do bot no servidor."""
        cursor = await self._db.execute(
            "SELECT bot_channel_id FROM guild_settings WHERE guild_id = ?", (guild_id,)
        )
        row = await cursor.fetchone()
        return row['bot_channel_id'] if row else None

    async def set_bot_channel(self, guild_id: int, channel_id: int | None):
        """Define o canal exclusivo do bot no servidor."""
        async with self._lock:
            await self._db.execute(
                """INSERT INTO guild_settings (guild_id, bot_channel_id)
                   VALUES (?, ?)
                   ON CONFLICT(guild_id) DO UPDATE SET bot_channel_id = excluded.bot_channel_id""",
                (guild_id, channel_id)
            )
            await self._db.commit()

    async def ignore_channel(self, channel_id: int):
        """Marca o canal (ticket) para ser ignorado pela IA futuramente."""
        async with self._lock:
            await self._db.execute("INSERT OR IGNORE INTO ignored_channels (channel_id) VALUES (?)", (channel_id,))
            await self._db.commit()

    async def unignore_channel(self, channel_id: int) -> bool:
        """Remove o canal da lista de ignorados pela IA."""
        async with self._lock:
            cursor = await self._db.execute("DELETE FROM ignored_channels WHERE channel_id = ?", (channel_id,))
            await self._db.commit()
            return cursor.rowcount > 0

    async def is_channel_ignored(self, channel_id: int) -> bool:
        """Verifica se o canal está na lista de ignorados."""
        cursor = await self._db.execute("SELECT 1 FROM ignored_channels WHERE channel_id = ?", (channel_id,))
        row = await cursor.fetchone()
        return row is not None

    async def count_ignored_channels(self) -> int:
        """Conta quantos canais estao pausados para a IA."""
        cursor = await self._db.execute("SELECT COUNT(*) AS c FROM ignored_channels")
        row = await cursor.fetchone()
        return row["c"] if row else 0

    async def get_ignored_channel_ids(self, limit: int = 20) -> list[int]:
        """Lista IDs de canais pausados para a IA."""
        cursor = await self._db.execute(
            "SELECT channel_id FROM ignored_channels ORDER BY channel_id DESC LIMIT ?",
            (max(1, limit),)
        )
        return [row["channel_id"] for row in await cursor.fetchall()]

    # ==================== SCAN CHANNELS (BASE DE CONHECIMENTO) ====================

    async def add_scan_channel(self, channel_id: int, guild_id: int, label: str) -> bool:
        """Adiciona canal à lista de varredura. Retorna False se já existia."""
        async with self._lock:
            from config import now_br
            try:
                await self._db.execute(
                    """INSERT INTO scan_channels (channel_id, guild_id, label, added_at)
                       VALUES (?, ?, ?, ?)""",
                    (channel_id, guild_id, label, now_br().isoformat())
                )
                await self._db.commit()
                return True
            except Exception:
                return False  # Já existe (PRIMARY KEY conflict)

    async def remove_scan_channel(self, channel_id: int) -> bool:
        """Remove canal da lista de varredura. Retorna True se removeu."""
        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM scan_channels WHERE channel_id = ?", (channel_id,)
            )
            await self._db.commit()
            return cursor.rowcount > 0

    async def get_scan_channels(self, guild_id: int) -> list:
        """Retorna todos os canais de varredura de um servidor."""
        cursor = await self._db.execute(
            "SELECT channel_id, guild_id, label, added_at FROM scan_channels WHERE guild_id = ? ORDER BY added_at",
            (guild_id,)
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_all_scan_guild_ids(self) -> list[int]:
        """Retorna IDs únicos de todos os servidores com canais configurados."""
        cursor = await self._db.execute(
            "SELECT DISTINCT guild_id FROM scan_channels"
        )
        return [row[0] for row in await cursor.fetchall()]


# Instância global
db = Database()
