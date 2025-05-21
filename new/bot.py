from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Text
from aiogram.types import CallbackQuery
import time
from aiogram import types
from aiogram.dispatcher.handler import CancelHandler
from aiogram.dispatcher.middlewares import BaseMiddleware

from db import Database
import config
from config import ADMIN_ID, TOKEN
import sqlite3

bot = Bot(token=config.TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
db = Database()

admin_phone = None


class SoftAntiSpamMiddleware(BaseMiddleware):
    def __init__(self, spam_window=5, max_clicks=3, block_duration=15):
        super().__init__()
        self.spam_window = spam_window
        self.max_clicks = max_clicks
        self.block_duration = block_duration
        self.user_data = {}  # user_id: {"timestamps": [...], "blocked_until": float}

    async def on_pre_process_callback_query(self, callback: types.CallbackQuery, data: dict):
        user_id = callback.from_user.id
        now = time.time()

        user_info = self.user_data.get(user_id, {"timestamps": [], "blocked_until": 0})

        # Agar bloklangan bo‘lsa
        if now < user_info["blocked_until"]:
            raise CancelHandler()

        # Eski vaqtlarni tozalaymiz
        user_info["timestamps"] = [ts for ts in user_info["timestamps"] if now - ts <= self.spam_window]
        user_info["timestamps"].append(now)

        # Spammi?
        if len(user_info["timestamps"]) > self.max_clicks:
            user_info["blocked_until"] = now + self.block_duration
            self.user_data[user_id] = user_info
            await callback.answer("❗️Siz antispamga tushdingiz, 15 soniya kuting.", show_alert=True)
            raise CancelHandler()

        # Ma’lumotni yangilaymiz
        self.user_data[user_id] = user_info

dp.middleware.setup(SoftAntiSpamMiddleware(
    spam_window=5,        # 5 soniya ichida
    max_clicks=3,         # 3 martadan ko‘p
    block_duration=15     # 15 soniya blok
))

# --- STATES ---
class Register(StatesGroup):
    waiting_for_phone = State()

class LocationStates(StatesGroup):
    waiting_for_location = State()

class AdminStates(StatesGroup):
    add_time = State()
    cancel_time = State()
    sql_query = State()
    broadcast_message = State() 

class BookingStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_surname = State()
    confirm_booking = State()


class ContactAdmin(StatesGroup):
    waiting_for_message = State()
    waiting_for_reply = State()

# --- REPLY BUTTONS ---
def main_menu(user_id=None):
    is_admin = db.is_admin(user_id) if user_id else False
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📅 Bo'sh vaqtlar", "📋 Bronlarim")
    kb.add("📍 Manzilimiz", "🆘 Admin bilan bog'lanish")
    
    if is_admin:
        kb.add("🛠 Admin panel")
    
    return kb


# --- INLINE BUTTONS ---
def time_buttons(times):
    markup = types.InlineKeyboardMarkup()
    for t in times:
        markup.add(types.InlineKeyboardButton(t, callback_data=f"time:{t}"))
    return markup

def confirm_time_menu(time):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Bron qilish", callback_data=f"book:{time}"),
        types.InlineKeyboardButton("🔙 Orqaga", callback_data="back")
    )
    return markup



def admin_panel():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ Bo'sh vaqt qo‘shish", callback_data="add_time"),
        types.InlineKeyboardButton("🗑 Bronni bekor qilish", callback_data="cancel_booking"),
    )
    kb.add(
        types.InlineKeyboardButton("📋 Bronlar", callback_data="show_bookings"),
        types.InlineKeyboardButton("🧹 Bo‘sh vaqtlarni tozalash", callback_data="clear_times")
    )
    return kb

@dp.callback_query_handler(lambda c: c.data == "clear_times")
async def confirm_clear_times(call: types.CallbackQuery):
    confirm_kb = types.InlineKeyboardMarkup(row_width=2)
    confirm_kb.add(
        types.InlineKeyboardButton("✅ Ha", callback_data="confirm_clear"),
        types.InlineKeyboardButton("❌ Yo‘q", callback_data="admin_back")  # Bu tugma ortga qaytaradi
    )
    await call.message.edit_text(
        "❗️Rostdan ham barcha bo‘sh vaqtlarni o‘chirmoqchimisiz?",
        reply_markup=confirm_kb
    )


@dp.callback_query_handler(lambda c: c.data == "confirm_clear")
async def clear_all_times(call: types.CallbackQuery):
    db.cursor.execute("DELETE FROM times")  # bo'sh vaqtlarni o'chirish
    db.conn.commit()
    
    await call.message.edit_text("✅ Barcha bo‘sh vaqtlar muvaffaqiyatli o‘chirildi.", reply_markup=admin_panel())
    
    
    
@dp.callback_query_handler(lambda c: c.data == "admin_back")
async def back_to_admin(call: types.CallbackQuery):
    await call.message.edit_text("🔧 Admin panel:", reply_markup=admin_panel())



def after_add_time_menu():
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("➕ Yana qo‘shish", callback_data="add_time"),
        types.InlineKeyboardButton("🔙 Menyuga qaytish", callback_data="admin_back")
    )
    return markup

def confirm_advertisement_menu():
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("📝 Yana e'lon yuborish", callback_data="resend_advertisement"),
        types.InlineKeyboardButton("⏹ To'xtatish", callback_data="stop_advertisement")
    )
    return markup

# --- START ---
@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    if db.is_registered(msg.from_user.id):
        await msg.answer("✅ Siz ro'yxatdan o'tgansiz.", reply_markup=main_menu(msg.from_user.id))
    else:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(types.KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True))
        await msg.answer("Telefon raqamingizni yuboring:", reply_markup=kb)
        await Register.waiting_for_phone.set()

@dp.message_handler(content_types=types.ContentType.CONTACT, state=Register.waiting_for_phone)
async def phone_handler(msg: types.Message, state: FSMContext):
    db.add_user(msg.from_user.id, msg.contact.phone_number)
    await msg.answer("🎉 Xush kelibsiz!", reply_markup=main_menu(msg.from_user.id))
    await state.finish()
    

# --- BO'SH VAQTLAR KO'RISH ---
@dp.message_handler(Text(equals="📅 Bo'sh vaqtlar"))
async def show_times(msg: types.Message):
    times = db.get_free_times()
    if not times:
        await msg.answer("⛔ Afsuski, hozircha bo‘sh vaqtlar yo‘q.")
        return
    await msg.answer("Bo'sh vaqtlar:", reply_markup=time_buttons(times))

@dp.callback_query_handler(lambda c: c.data == "back")
async def back_to_times(call: types.CallbackQuery):
    times = db.get_free_times()
    if not times:
        await call.message.edit_text("⛔ Bo'sh vaqtlar qolmagan.")
        return
    await call.message.edit_text("Bo'sh vaqtlar:", reply_markup=time_buttons(times))

@dp.callback_query_handler(lambda c: c.data.startswith("time:"))
async def select_time(call: types.CallbackQuery):
    time = call.data.split(":")[1]
    if db.is_time_booked(time):
        await call.answer("Bu vaqt allaqachon band qilingan!", show_alert=True)
        return
    await call.message.edit_text(f"Tanlangan vaqt: {time}", reply_markup=confirm_time_menu(time))

@dp.callback_query_handler(lambda c: c.data.startswith("book:"))
async def book_selected_time(call: types.CallbackQuery, state: FSMContext):
    time = call.data.split(":")[1]
    user_id = call.from_user.id

    if db.has_booking_today(user_id):
        await call.message.edit_text("⚠️ Siz bugun allaqachon bir marta bron qilgansiz.")
        return

    if db.is_time_booked(time):
        await call.message.edit_text("❌ Bu vaqt allaqachon band qilingan.")
        return

    await state.update_data(time=time)
    await call.message.answer("Ismingizni kiriting:")
    await BookingStates.waiting_for_name.set()

@dp.message_handler(state=BookingStates.waiting_for_name)
async def get_name(msg: types.Message, state: FSMContext):
    await state.update_data(name=msg.text)
    await msg.answer("Familiyangizni kiriting:")
    await BookingStates.waiting_for_surname.set()

@dp.message_handler(state=BookingStates.waiting_for_surname)
async def get_surname(msg: types.Message, state: FSMContext):
    await state.update_data(surname=msg.text)
    data = await state.get_data()
    phone = db.get_user_phone(msg.from_user.id)

    confirm_text = (
        f"🔒 Quyidagi ma'lumotlar to‘g‘rimi?\n\n"
        f"👤 Ism: {data['name']}\n"
        f"👤 Familiya: {data['surname']}\n"
        f"📞 Telefon: {phone}\n"
        f"🕒 Vaqt: {data['time']}"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Tasdiqlash", callback_data="confirm_booking"),
        types.InlineKeyboardButton("🔙 Menyuga qaytish", callback_data="cancel_booking_process")
    )

    await msg.answer(confirm_text, reply_markup=markup)
    await BookingStates.confirm_booking.set()

@dp.callback_query_handler(lambda c: c.data == "confirm_booking", state=BookingStates.confirm_booking)
async def confirm_booking(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    data = await state.get_data()
    phone = db.get_user_phone(user_id)

    db.book_time(user_id, data['time'])
    db.delete_time(data['time'])

    for admin in db.get_all_admins():
        await bot.send_message(
            admin[0],
            f"📥 Yangi bron:\n"
            f"👤 Ism: {data['name']}\n"
            f"👤 Familiya: {data['surname']}\n"
            f"📞 Tel: {phone}\n"
            f"🕒 Vaqt: {data['time']}"
        )

    await call.message.edit_text("✅ So‘rov adminga yuborildi. Bron tasdiqlandi.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "cancel_booking_process", state=BookingStates.confirm_booking)
async def cancel_booking_process(call: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await call.message.edit_text("❌ Bron bekor qilindi. Menyuga qaytdingiz.", reply_markup=main_menu())

# --- BRONLARIM VA QOLGAN ADMIN FUNKSIYALARI (o'zgartirilmagan) ---
# (Qolgan kod o'zgarishsiz saqlanadi - SQL, addadmin, va boshqalar)


# --- FOYDALANUVCHINING BRONLARI ---
@dp.message_handler(Text(equals="📋 Bronlarim"))
async def my_bookings(msg: types.Message):
    bookings = db.get_user_bookings(msg.from_user.id)
    if not bookings:
        await msg.answer("⛔ Sizda bron yo'q.")
        return
    text = "\n".join([f"{t[0]} - {t[1]}" for t in bookings])
    await msg.answer("📋 Bronlaringiz:\n" + text)

# --- ADMIN PANEL ---
@dp.message_handler(commands=['admin'])
async def admin_panel_cmd(msg: types.Message):
    if db.is_admin(msg.from_user.id):
        await msg.answer("🔧 Admin panel:", reply_markup=admin_panel())
    else:
        await msg.answer("⛔ Sizda ruxsat yo‘q.")

@dp.callback_query_handler(lambda c: c.data == "add_time")
async def start_add_time(call: types.CallbackQuery):
    await call.message.answer("🕒 Qo‘shiladigan vaqtni kiriting (masalan: 15:30):")
    await AdminStates.add_time.set()

@dp.message_handler(state=AdminStates.add_time)
async def add_time_input(msg: types.Message, state: FSMContext):
    db.add_time(msg.text.strip())
    await msg.answer("✅ Vaqt qo‘shildi.", reply_markup=types.ReplyKeyboardRemove())
    await msg.answer("Yana davom etasizmi?", reply_markup=after_add_time_menu())
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "admin_back")
async def back_to_admin(call: types.CallbackQuery):
    await call.message.edit_text("🔧 Admin panel:", reply_markup=admin_panel())

@dp.callback_query_handler(lambda c: c.data == "cancel_booking")
async def start_cancel_time(call: types.CallbackQuery):
    await call.message.answer("🗑 Bekor qilinadigan vaqtni kiriting:")
    await AdminStates.cancel_time.set()

@dp.message_handler(state=AdminStates.cancel_time)
async def cancel_time_input(msg: types.Message, state: FSMContext):
    db.cancel_booking(msg.text.strip())
    await msg.answer("❌ Bron bekor qilindi.")
    await state.finish()

# add_time_slot funksiyasi
async def add_time_slot(time: str):
    async with sqlite3.connect("bot.db") as db:
        # Avval mavjudligini tekshiramiz
        cursor = await db.execute("SELECT id FROM available_times WHERE time = ?", (time,))
        exists = await cursor.fetchone()
        
        if exists:
            return False  # Bu vaqt allaqachon mavjud

        # Agar mavjud bo'lmasa, qo'shamiz
        await db.execute("INSERT INTO available_times (time, created_at) VALUES (?, datetime('now'))", (time,))
        await db.commit()
        return True
    
@dp.callback_query_handler(lambda c: c.data.startswith('add_time:'))
async def add_time_callback(callback_query: CallbackQuery):
    time = callback_query.data.split(':')[1]
    success = await add_time_slot(time)
    if success:
        await callback_query.answer("Bo'sh vaqt qo'shildi.")
    else:
        await callback_query.answer("Bu vaqt allaqachon mavjud!", show_alert=True)



@dp.callback_query_handler(lambda c: c.data == "show_bookings")
async def show_bookings(call: types.CallbackQuery):
    data = db.get_all_bookings()
    if not data:
        await call.message.answer("📭 Hech qanday bron yo‘q.")
        return
    text = "\n".join([f"👤 {r[0]} | 🕒 <code>{r[1]}</code> | 📌 {r[2]}" for r in data])
    await call.message.answer("📋 Barcha bronlar:\n" + text, parse_mode="HTML")

@dp.message_handler(commands=['addadmin'])
async def add_admin_cmd(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo‘q.")
        return

    args = msg.get_args()
    if not args.isdigit():
        await msg.answer("⚠️ Foydalanuvchi ID raqamini to‘g‘ri ko‘rsating. Misol: /addadmin 123456789")
        return

    user_id = int(args)
    db.add_admin(user_id)
    await msg.answer(f"✅ Admin muvaffaqiyatli qo‘shildi: {user_id}")


@dp.message_handler(commands=['sql'])
async def sql_command(msg: types.Message):
    # Faoliyatni faqat 7911495400 id egasiga ruxsat berish
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("🔎 Iltimos, SQL so'rovini kiriting:")
        await AdminStates.sql_query.set()
    else:
        await msg.answer("⛔ Sizda ruxsat yo'q.")

@dp.message_handler(state=AdminStates.sql_query)
async def handle_sql_query(msg: types.Message, state: FSMContext):
    sql_query = msg.text.strip()

    # So'rovni bajarish va natijani olish
    try:
        execution_time, results = db.execute_sql_with_time(sql_query)

        # Natijalarni yuborish
        if results:
            result_text = "\n".join([str(row) for row in results])
        else:
            result_text = "So'rov natijasida hech narsa topilmadi."

        await msg.answer(f"📊 So'rov bajarildi.\nVaqt: {execution_time:.5f} sekund\n\nNatijalar:\n{result_text}")
    except Exception as e:
        await msg.answer(f"❌ Xato: {e}")
    
    await state.finish()

@dp.message_handler(commands=['addsqlpermissions'])
async def add_sql_permissions(msg: types.Message):
    if msg.from_user.id == ADMIN_ID:
        args = msg.get_args()
        if not args.isdigit():
            await msg.answer("⚠️ Iltimos, foydalanuvchi ID raqamini to'g'ri kiriting. Masalan: /addsqlpermissions 123456789")
            return
        
        user_id = int(args)
        # Foydalanuvchiga SQL so'rovini bajarish huquqini berish
        db.add_admin(user_id)  # adminlar jadvaliga qo'shish
        await msg.answer(f"✅ Foydalanuvchi {user_id} ga SQL so'rovini yuborish huquqi berildi.")
    else:
        await msg.answer("⛔ Sizda bu amalni bajarish uchun ruxsat yo'q.")


@dp.message_handler(commands=['br'])
async def br_command(msg: types.Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("📝 E'lon yuborish uchun matn kiriting:")
        await AdminStates.broadcast_message.set()
    else:
        await msg.answer("⛔ Sizda bu amalni bajarish huquqi yo'q.")


@dp.message_handler(state=AdminStates.broadcast_message)
async def handle_broadcast(msg: types.Message, state: FSMContext):
    users = db.get_all_users()
    count = 0
    for user in users:
        try:
            await bot.send_message(user[0], msg.text)
            count += 1
        except:
            continue
    await msg.answer(f"✅ E'lon {count} ta foydalanuvchiga yuborildi.")
    await state.finish()
    
@dp.message_handler(commands=['location'])
async def ask_for_location(message: types.Message):
    if message.from_user.id == ADMIN_ID:  # faqat admin uchun
        await message.answer("Iltimos, lokatsiyani yuboring:")
        await LocationStates.waiting_for_location.set()
    else:
        await message.answer("Bu buyruq faqat admin uchun.")

@dp.message_handler(content_types=types.ContentType.LOCATION, state=LocationStates.waiting_for_location)
async def receive_location(message: types.Message, state: FSMContext):
    latitude = message.location.latitude
    longitude = message.location.longitude

    db = sqlite3.connect('bot.db')
    cursor = db.cursor()
    cursor.execute("DELETE FROM location")  # eski manzilni o'chirish
    cursor.execute("INSERT INTO location (latitude, longitude) VALUES (?, ?)", (latitude, longitude))
    db.commit()
    db.close()

    await message.answer("Lokatsiya saqlandi!")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📍 Manzilimiz")
async def send_location_to_user(message: types.Message):
    db = sqlite3.connect('bot.db')
    cursor = db.cursor()
    cursor.execute("SELECT latitude, longitude FROM location ORDER BY id DESC LIMIT 1")
    location = cursor.fetchone()
    db.close()

    if location:
        latitude, longitude = location
        await message.answer_location(latitude=latitude, longitude=longitude)
        await message.answer(f"📍 Manzilimiz: https://maps.google.com/?={latitude},{longitude}", disable_web_page_preview=True)
    else:
        await message.answer("Hozircha lokatsiya mavjud emas.")

@dp.message_handler(commands=['stats'])
async def show_stats(message: types.Message):
    print("Stats buyrug'i ishga tushdi")  # debug
    if message.from_user.id == ADMIN_ID:
        conn = sqlite3.connect('bot.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        conn.close()
        await message.answer(f"👥 Umumiy foydalanuvchilar: {count}")
    else:
        await message.answer("❌ Sizda ruxsat yo‘q.")

@dp.message_handler(commands=['commands'])
async def show_commands(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        commands_text = (
            "🔐 <b>ADMIN UCHUN BUYRUQLAR:</b>\n\n"
            "🛠 /admin - admin panel\n"
            "📊 /stats - umumiy foydalanuvchilar\n"
            "🗄 /sql - database bilan ishlash\n"
            "📍 /location - manzil qo'shish\n"
            "➕ /addadmin - faqat katta admin uchun, admin qo'shish buyrug'i\n"
            "📢 /br - e'lon berish"
        )
        await message.answer(commands_text, parse_mode="HTML")
    else:
        await message.answer("❌ Sizda bu buyruqdan foydalanishga ruxsat yo‘q.")


@dp.message_handler(commands=['phone'])
async def set_admin_phone(message: types.Message):
    global admin_phone
    if message.from_user.id == ADMIN_ID:
        phone = message.get_args()
        if phone:
            admin_phone = phone
            await message.answer(f"✅ Telefon raqami saqlandi: {phone}")
        else:
            await message.answer("❗ Iltimos, telefon raqamni formatda yuboring:\n/phone +998901234567")
    else:
        await message.answer("❌ Sizga bu buyruqdan foydalanish taqiqlangan.")


@dp.message_handler(lambda message: message.text == "🆘 Admin bilan bog'lanish")
async def contact_admin(message: types.Message):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📨 Adminga xabar", callback_data="msg_to_admin"))

    text = "Admin bilan bog‘lanish uchun quyidagilardan birini tanlang:"
    if admin_phone:
        text += f"\n\n📞 Admin raqami: <code>{admin_phone}</code>"

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query_handler(lambda c: c.data == "msg_to_admin")
async def ask_user_message(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("✍️ Adminga yuboriladigan xabarni yozing:")
    await ContactAdmin.waiting_for_message.set()
    await state.update_data(user_id=callback.from_user.id, user_name=callback.from_user.full_name)
    await callback.answer()

@dp.message_handler(state=ContactAdmin.waiting_for_message, content_types=types.ContentTypes.TEXT)
async def forward_to_admin(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data['user_id']
    user_name = data['user_name']
    text = message.text

    # Admin uchun javob tugmasi
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✉️ Javob berish", callback_data=f"reply_{user_id}"))

    await bot.send_message(ADMIN_ID,
        f"📩 Yangi xabar:\n👤 <b>{user_name}</b>\n🆔 <code>{user_id}</code>\n\n{text}",
        parse_mode="HTML", reply_markup=kb
    )
    await message.answer("✅ Xabaringiz adminga yuborildi.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith("reply_"))
async def start_reply(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    await state.update_data(reply_user_id=user_id)
    await callback.message.answer("✍️ Foydalanuvchiga yuboriladigan javobni yozing:")
    await ContactAdmin.waiting_for_reply.set()
    await callback.answer()

@dp.message_handler(state=ContactAdmin.waiting_for_reply, content_types=types.ContentTypes.TEXT)
async def send_admin_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data['reply_user_id']
    reply_text = message.text

    try:
        await bot.send_message(user_id, f"📬 Sizga adminga yozgan xabaringizga javob keldi:\n\n<b>{reply_text}</b>", parse_mode="HTML")
        await message.answer("✅ Javob yuborildi.")
    except:
        await message.answer("❌ Xabar yuborib bo‘lmadi. Foydalanuvchi botni bloklagan bo‘lishi mumkin.")
    
    await state.finish()



@dp.callback_query_handler(lambda c: c.data.startswith("save_times"))
async def save_times_handler(callback_query: CallbackQuery):
    # ... admin tanlagan vaqtlar bazaga yoziladi

    # Vaqtlar qo‘shilgach, eski vaqtlarni tozalash
    await remove_expired_times()
    
    await callback_query.message.answer("✅ Yangi vaqtlar qo‘shildi va eskilari tozalandi.")

async def remove_expired_times():
    now = datetime.now()

    # Bo'sh (bron qilinmagan) vaqtlarni o'chirish
    cursor.execute("SELECT id, time FROM times")
    times = cursor.fetchall()
    for tid, t in times:
        try:
            time_obj = datetime.strptime(t, "%Y-%m-%d %H:%M")
            if time_obj < now:
                cursor.execute("DELETE FROM times WHERE id = ?", (tid,))
        except Exception as e:
            print(f"Xatolik vaqt o‘chirishda: {e}")

    # Bron muddati o'tgan foydalanuvchilarga xabar yuborish
    cursor.execute("SELECT id, user_id, time FROM bookings")
    bookings = cursor.fetchall()
    for bid, user_id, t in bookings:
        try:
            time_obj = datetime.strptime(t, "%Y-%m-%d %H:%M")
            if time_obj < now:
                try:
                    await bot.send_message(user_id, "⏰ Broningizning muddati o‘tgan.")
                except Exception as e:
                    print(f"Xabar yuborib bo‘lmadi: {e}")
                cursor.execute("DELETE FROM bookings WHERE id = ?", (bid,))
        except Exception as e:
            print(f"Xatolik bronni tekshirishda: {e}")

    db.commit()
    
@dp.message_handler(lambda msg: msg.text == "🛠 Admin panel")
async def show_admin_panel(msg: types.Message):
    if db.is_admin(msg.from_user.id):
        await admin_panel_cmd(msg)  # Bu sizda mavjud /admin komandasi funksiyasi
    else:
        await msg.answer("❌ Sizda admin panelga kirish huquqi yo'q.")



# --- RUN ---
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
