"""Tiny gettext-style i18n. Language resolved per request (query ?lang=, cookie, Accept-Language) into a contextvar.

Catalog keys are the English strings. `_()` returns the translation or the key itself.
"""
from __future__ import annotations

from contextvars import ContextVar

LANGUAGES = {"en": "English", "es": "Español"}
import os

DEFAULT_LANG = os.environ.get("DAVISH_DEFAULT_LANG", "es")
LANG_COOKIE = "davish_lang"
_current: ContextVar[str] = ContextVar("lang", default=DEFAULT_LANG)


def set_lang(lang: str) -> None:
    _current.set(lang if lang in LANGUAGES else DEFAULT_LANG)


def get_lang() -> str:
    return _current.get()


EN_LABELS = {
    "policy_flexible": "full refund until 24h before check-in", "policy_moderate": "full refund until 5 days before, 50% until 24h before",
    "policy_strict": "full refund until 14 days before, 50% until 7 days before",
    "tab_overview": "Overview", "tab_users": "Users", "tab_listings": "Listings", "tab_bookings": "Bookings", "Mar_": "Mar",
    "awaiting_payment": "awaiting payment",
}


def _(text: str) -> str:
    if get_lang() == "en":
        return EN_LABELS.get(text, text)
    return CATALOG.get(get_lang(), {}).get(text, EN_LABELS.get(text, text))


def negotiate(query_lang: str | None, cookie_lang: str | None, accept_language: str | None) -> str:
    for cand in (query_lang, cookie_lang):
        if cand in LANGUAGES:
            return cand
    for part in (accept_language or "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LANGUAGES:
            return code
    return DEFAULT_LANG


ES = {
    # nav / base
    "Explore": "Explorar", "Trips": "Reservas", "Hosting": "Anfitrión", "Become a host": "Hazte anfitrión", "Log out": "Cerrar sesión",
    "Log in": "Iniciar sesión", "Sign up": "Registrarse", "Apartments by the hour": "Apartamentos por horas",
    "List your apartment": "Publica tu apartamento", "API": "API", "Language": "Idioma",
    # home
    "Apartments by the hour.": "Apartamentos por horas.", "Not by the night.": "No por noches.",
    "A shower between flights, a quiet afternoon to work, a place to rest before a late train. Pick a day, choose your hours, book instantly.":
        "Una ducha entre vuelos, una tarde tranquila para trabajar, un lugar donde descansar antes de un tren nocturno. Elige un día, elige tus horas y reserva al instante.",
    "Browse by size": "Explorar por tamaño", "Popular cities": "Ciudades populares", "Top-rated apartments": "Apartamentos mejor valorados",
    "How it works": "Cómo funciona", "Search by time": "Busca por horario",
    "Tell us where and when. We only show apartments that are free for your whole slot.": "Dinos dónde y cuándo. Solo mostramos apartamentos libres durante todo tu horario.",
    "Pick your hours": "Elige tus horas",
    "Choose a start and end time in 30-minute steps. Prices are quoted per hour, no nightly minimums.": "Elige hora de inicio y fin en pasos de 30 minutos. Los precios son por hora, sin mínimo de noches.",
    "Book and go": "Reserva y listo",
    "Instant confirmation on most apartments. Hosts get automatic cleaning buffers between bookings.": "Confirmación inmediata en la mayoría de apartamentos. Los anfitriones tienen márgenes de limpieza automáticos entre reservas.",
    # sizes / amenities / weekdays
    "Studio": "Estudio", "1 bedroom": "1 dormitorio", "2 bedrooms": "2 dormitorios", "3+ bedrooms": "3+ dormitorios",
    "Compact and private. Rest, shower, work.": "Compacto y privado. Descansa, dúchate, trabaja.",
    "A real bedroom plus a living space.": "Un dormitorio de verdad más un salón.",
    "Room for a small group or a family.": "Espacio para un grupo pequeño o una familia.",
    "Large flats for gatherings and day events.": "Pisos grandes para reuniones y eventos de día.",
    "Wi-Fi": "Wi-Fi", "Air conditioning": "Aire acondicionado", "Heating": "Calefacción", "Full kitchen": "Cocina completa",
    "Coffee & tea": "Café y té", "Shower": "Ducha", "Bathtub": "Bañera", "Washer / dryer": "Lavadora / secadora", "TV": "TV",
    "Workspace": "Zona de trabajo", "Balcony": "Balcón", "Natural light": "Luz natural", "Elevator": "Ascensor",
    "Wheelchair accessible": "Accesible en silla de ruedas", "Parking": "Aparcamiento", "Pet friendly": "Admite mascotas",
    "Doorman": "Portero", "Self check-in": "Entrada autónoma", "Bed linens": "Ropa de cama", "Blackout curtains": "Cortinas opacas",
    "Crib": "Cuna", "Gym access": "Acceso a gimnasio", "Pool access": "Acceso a piscina",
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
    "Mon": "Lun", "Tue": "Mar", "Wed": "Mié", "Thu": "Jue", "Fri": "Vie", "Sat": "Sáb", "Sun": "Dom",
    "Jan": "ene", "Feb": "feb", "Mar_": "mar", "Apr": "abr", "May": "may", "Jun": "jun", "Jul": "jul", "Aug": "ago", "Sep": "sep", "Oct": "oct", "Nov": "nov", "Dec": "dic",
    # search bar / search
    "Where": "Dónde", "City or neighborhood": "Ciudad o barrio", "Date": "Fecha", "From": "Desde", "To": "Hasta", "People": "Personas", "Any": "Cualq.",
    "Search": "Buscar", "Any size": "Cualquier tamaño", "Any price": "Cualquier precio", "Up to": "Hasta", "Explore apartments": "Explorar apartamentos",
    "Apartments in": "Apartamentos en", "apartment": "apartamento", "apartments": "apartamentos", "available on": "disponibles el",
    "from": "de", "to": "a", "No apartments match yet": "Todavía no hay apartamentos que coincidan",
    "Try a different time window, a nearby city, or fewer filters.": "Prueba otro horario, una ciudad cercana o menos filtros.",
    "Request to book": "Solicitar reserva", "Instant": "Inmediata", "New": "Nuevo", "bed": "cama", "beds": "camas", "bath": "baño",
    "up to": "hasta", "guest": "huésped", "guests": "huéspedes", "min": "mín", "/ hour": "/ hora", "Paused": "Pausado",
    # listing page
    "This listing is paused and only visible to you.": "Este anuncio está pausado y solo tú puedes verlo.", "Edit": "Editar", "Calendar": "Calendario",
    "Hosted by": "Anfitrión:", "Instant booking": "Reserva inmediata", "Booking requests are reviewed by the host": "El anfitrión revisa cada solicitud de reserva",
    "hour bookings": "horas por reserva", "min cleaning buffer between bookings": "min de margen de limpieza entre reservas",
    "Amenities": "Servicios", "Opening hours": "Horario", "Closed": "Cerrado", "Reviews": "Reseñas", "No reviews yet.": "Todavía no hay reseñas.",
    "Location": "Ubicación", "The exact address and entry instructions are shared after booking.": "La dirección exacta y las instrucciones de entrada se envían tras la reserva.",
    "cleaning": "limpieza", "This is your apartment.": "Este es tu apartamento.", "Loading availability…": "Cargando disponibilidad…",
    "Note to host (optional)": "Nota para el anfitrión (opcional)", "What do you need the apartment for?": "¿Para qué necesitas el apartamento?",
    "Hours": "Horas", "Subtotal": "Subtotal", "Cleaning fee": "Limpieza", "Service fee": "Comisión de servicio", "Total": "Total",
    "Book now": "Reservar ahora", "Log in to book": "Inicia sesión para reservar",
    "Free cancellation up to 24 hours before start.": "Cancelación gratuita hasta 24 horas antes del inicio.",
    "review": "reseña", "reviews": "reseñas", "midnight": "medianoche",
    # booking.js
    "Closed on this day. Pick another date.": "Cerrado este día. Elige otra fecha.", "Tap a start time, then an end time.": "Toca una hora de inicio y luego una de fin.",
    "Fully booked on this day.": "Completo este día.", "Those hours are not all free — pick a contiguous range.": "No todas esas horas están libres: elige un rango continuo.",
    "Start:": "Inicio:", "now pick an end time": "ahora elige la hora de fin", "hour": "hora", "hours": "horas", "minimum": "mínimo", "maximum": "máximo", "max": "máx",
    # booking page
    "Booking": "Reserva", "You're booked!": "¡Reserva confirmada!", "is yours on": "es tuyo el",
    "Request sent.": "Solicitud enviada.", "will respond soon. You won't be charged until it's accepted.": "responderá pronto. No se te cobrará hasta que la acepte.",
    "Payment was not completed.": "El pago no se completó.", "Your slot is held for a short time while you pay.": "Tu horario queda reservado un breve tiempo mientras pagas.",
    "Pay": "Pagar", "now": "ahora", "Pay now": "Pagar ahora", "Guest:": "Huésped:", "Status": "Estado", "Time": "Hora", "Address": "Dirección", "Note": "Nota",
    "Payment": "Pago", "refunded": "reembolsado", "(simulated: Stripe keys not set)": "(simulado: faltan las claves de Stripe)",
    "Accept request": "Aceptar solicitud", "Decline": "Rechazar", "Cancel booking": "Cancelar reserva", "Cancel this booking?": "¿Cancelar esta reserva?",
    "Leave a review": "Escribir una reseña", "Rating": "Valoración", "Review": "Reseña", "Submit review": "Enviar reseña", "View listing": "Ver anuncio",
    "Messages": "Mensajes", "No messages yet.": "Todavía no hay mensajes.", "Write a message…": "Escribe un mensaje…", "Send": "Enviar",
    "Price breakdown": "Desglose del precio", "h × rate": "h × tarifa", "Total charged": "Total cobrado", "Your payout": "Tu ingreso", "made": "creada el",
    # statuses
    "awaiting_payment": "pendiente de pago", "pending": "pendiente", "confirmed": "confirmada", "declined": "rechazada", "cancelled": "cancelada",
    "expired": "caducada", "completed": "completada", "unpaid": "sin pagar", "authorized": "autorizado", "paid": "pagado", "disputed": "en disputa",
    "All": "Todas",
    # trips
    "Your trips": "Tus reservas", "Your bookings": "Tus reservas", "Upcoming": "Próximas", "Past": "Pasadas",
    "No upcoming bookings.": "No tienes reservas próximas.", "Find a space": "Busca un apartamento", "Nothing here yet.": "Todavía nada por aquí.", "Review pending": "Reseña pendiente",
    # auth
    "Welcome back": "Hola de nuevo", "Email": "Correo electrónico", "Password": "Contraseña", "New here?": "¿Eres nuevo?", "Create an account": "Crea una cuenta",
    "Forgot your password?": "¿Olvidaste tu contraseña?", "Start hosting": "Empieza como anfitrión", "Create your account": "Crea tu cuenta", "Name": "Nombre",
    "I want to list a space": "Quiero publicar un apartamento", "Already have an account?": "¿Ya tienes cuenta?",
    "Reset your password": "Restablece tu contraseña", "Reset password": "Restablecer contraseña",
    "If an account exists for": "Si existe una cuenta para", "we've emailed a reset link. It expires in 60 minutes.": "te hemos enviado un enlace por correo. Caduca en 60 minutos.",
    "Back to log in": "Volver a iniciar sesión", "Enter your email and we'll send you a link to choose a new password.": "Escribe tu correo y te enviaremos un enlace para elegir una nueva contraseña.",
    "Send reset link": "Enviar enlace", "Choose a new password": "Elige una nueva contraseña", "New password": "Nueva contraseña", "Confirm password": "Confirmar contraseña",
    "Save password": "Guardar contraseña", "Account": "Cuenta", "Your account": "Tu cuenta", "Password updated. You're logged in.": "Contraseña actualizada. Has iniciado sesión.",
    "Changes saved.": "Cambios guardados.", "Change password": "Cambiar contraseña", "Current password": "Contraseña actual", "Leave blank to keep": "Deja en blanco para no cambiarla",
    "Save changes": "Guardar cambios", "Member since": "Miembro desde", "Host account": "Cuenta de anfitrión", "Guest account": "Cuenta de huésped",
    "Delete account": "Eliminar cuenta", "Confirm with your password": "Confirma con tu contraseña", "Delete my account": "Eliminar mi cuenta",
    "Delete your account? This cannot be undone.": "¿Eliminar tu cuenta? No se puede deshacer.",
    # errors page
    "Oops": "Vaya", "Something's off": "Algo no cuadra", "Back home": "Volver al inicio", "Request a new one": "Solicitar otro", "View booking": "Ver reserva",
    # host
    "Hosting dashboard": "Panel de anfitrión", "New listing": "Nuevo anuncio", "Earnings": "Ingresos", "Hours booked": "Horas reservadas", "Bookings": "Reservas",
    "Pending requests": "Solicitudes pendientes", "Your listings": "Tus anuncios", "no reviews": "sin reseñas", "You haven't listed anything yet.": "Todavía no has publicado nada.",
    "Create your first listing": "Crea tu primer anuncio", "Recent bookings": "Reservas recientes", "See all": "Ver todas", "No bookings yet.": "Todavía no hay reservas.",
    "people": "personas", "Edit apartment": "Editar apartamento", "Basics": "Datos básicos", "Title": "Título", "Bedrooms": "Dormitorios", "Bathrooms": "Baños",
    "Beds": "Camas", "Description": "Descripción", "City": "Ciudad", "Neighborhood": "Barrio", "Street address (shared after booking)": "Dirección (se comparte tras la reserva)",
    "Photo URLs (one per line)": "URLs de fotos (una por línea)", "Pricing & rules": "Precio y normas", "Hourly rate ($)": "Tarifa por hora ($)", "Cleaning fee ($)": "Tarifa de limpieza ($)",
    "Guests (max)": "Huéspedes (máx.)", "Cleaning buffer (min)": "Margen de limpieza (min)", "Minimum hours": "Horas mínimas", "Maximum hours": "Horas máximas",
    "Timezone of the apartment": "Zona horaria del apartamento", "Instant booking (otherwise you approve each request)": "Reserva inmediata (si no, apruebas cada solicitud)",
    "Active": "Activo", "Bookings must fit inside one window on a single day. Use \"24:00\" for midnight.": "Cada reserva debe caber en una franja de un mismo día. Usa \"24:00\" para medianoche.",
    "Publish listing": "Publicar anuncio", "Blocked time": "Horas bloqueadas",
    "Block hours for maintenance or private use. Guests can't book overlapping times.": "Bloquea horas para mantenimiento o uso privado. Los huéspedes no podrán reservarlas.",
    "No upcoming blocks.": "No hay bloqueos próximos.", "Remove": "Quitar", "Reason (optional)": "Motivo (opcional)", "Add block": "Añadir bloqueo",
    "Week of": "Semana del", "Prev": "Anterior", "Next": "Siguiente", "free": "libre",
    # server-side messages
    "Listing not found.": "Anuncio no encontrado.", "Booking not found.": "Reserva no encontrada.", "Wrong email or password.": "Correo o contraseña incorrectos.",
    "Password must be at least 8 characters.": "La contraseña debe tener al menos 8 caracteres.", "Please enter your name and a valid email.": "Escribe tu nombre y un correo válido.",
    "An account with that email already exists.": "Ya existe una cuenta con ese correo.", "You can only review a completed stay once.": "Solo puedes reseñar una estancia completada, y una sola vez.",
    "Switch to a host account to access hosting tools.": "Cambia a una cuenta de anfitrión para usar estas herramientas.",
    "This reset link is invalid or has expired.": "Este enlace no es válido o ha caducado.", "Passwords must match and be at least 8 characters.": "Las contraseñas deben coincidir y tener al menos 8 caracteres.",
    "Name and a valid email are required.": "Se necesita un nombre y un correo válido.", "That email is already in use.": "Ese correo ya está en uso.",
    "Current password is wrong.": "La contraseña actual es incorrecta.", "New password must be at least 8 characters.": "La nueva contraseña debe tener al menos 8 caracteres.",
    "Password is wrong.": "Contraseña incorrecta.", "Cancel or complete your active bookings before deleting the account.": "Cancela o completa tus reservas activas antes de eliminar la cuenta.",
    "Please check the numeric fields.": "Revisa los campos numéricos.", "Title and city are required.": "El título y la ciudad son obligatorios.",
    "Hourly rate must be greater than zero.": "La tarifa por hora debe ser mayor que cero.", "Pick a valid timezone.": "Elige una zona horaria válida.",
    "Check the minimum / maximum hours.": "Revisa las horas mínimas / máximas.", "Set opening hours for at least one day.": "Define el horario de al menos un día.",
    "Listing is not available for booking.": "Este anuncio no admite reservas.", "You cannot book your own listing.": "No puedes reservar tu propio anuncio.",
    "This space holds up to %s people.": "Este apartamento admite hasta %s personas.", "Times must be formatted YYYY-MM-DDTHH:MM.": "Las horas deben tener el formato AAAA-MM-DDTHH:MM.",
    "End time must be after start time.": "La hora de fin debe ser posterior a la de inicio.", "Start time is in the past.": "La hora de inicio ya ha pasado.",
    "Times must be in %s-minute steps.": "Las horas deben ir en pasos de %s minutos.", "A booking must start and end on the same day.": "La reserva debe empezar y terminar el mismo día.",
    "Minimum booking is %s hours.": "La reserva mínima es de %s horas.", "Maximum booking is %s hours.": "La reserva máxima es de %s horas.",
    "The space is not open for the whole requested time.": "El apartamento no está disponible durante todo el horario solicitado.",
    "Those hours are no longer available.": "Esas horas ya no están disponibles.", "This booking is not awaiting payment.": "Esta reserva no está pendiente de pago.",
    "Payment could not be started: %s": "No se pudo iniciar el pago: %s", "Only pending requests can be accepted or declined.": "Solo se pueden aceptar o rechazar solicitudes pendientes.",
    "Stripe error: %s": "Error de Stripe: %s", "This booking can no longer be cancelled.": "Esta reserva ya no se puede cancelar.", "The booking has already started.": "La reserva ya ha empezado.",
    "Sign in required": "Debes iniciar sesión", "Host account required": "Se necesita una cuenta de anfitrión",
}

ES.update({
    " by the guest": " por el huésped", " by the host": " por el anfitrión",
    "%s wrote:\n\n%s\n\nReply here: %s\n": "%s escribió:\n\n%s\n\nResponde aquí: %s\n",
    "/ day": "/ día", "About you": "Sobre ti", "Activate": "Activar", "Add photos": "Añadir fotos", "Add price rule": "Añadir regla de precio",
    "Address: %s": "Dirección: %s", "Admin": "Admin", "Advance notice": "Antelación mínima", "Advance notice (hours)": "Antelación mínima (horas)",
    "Apartments with hourly precision": "Apartamentos con precisión horaria", "Apartments with hourly precision.": "Apartamentos con precisión horaria.",
    "Apply": "Aplicar", "Availability & prices": "Disponibilidad y precios", "Availability rules": "Normas de disponibilidad", "Best rated": "Mejor valorados",
    "Booking cancelled: %s": "Reserva cancelada: %s", "Booking confirmed: %s": "Reserva confirmada: %s", "Booking request: %s": "Solicitud de reserva: %s",
    "Booking window (days ahead)": "Ventana de reserva (días de antelación)", "Bookings can be made at most %s days in advance.": "Solo se puede reservar con un máximo de %s días de antelación.",
    "Calendar & pricing": "Calendario y precios", "Cancel": "Cancelar", "Cancellation": "Cancelación", "Cancellation policy": "Política de cancelación",
    "Check in and out at any hour and pay only for the time you use: a shower between flights, a night, a working week. Pick your check-in and check-out to the hour and book instantly.":
        "Entra y sal a cualquier hora y paga solo por el tiempo que usas: una ducha entre vuelos, una noche, una semana de trabajo. Elige tu entrada y salida a la hora exacta y reserva al instante.",
    "Check the rule fields: dates, rate and hour range.": "Revisa los campos de la regla: fechas, tarifa y rango de horas.",
    "Check-in": "Entrada", "Check-in from": "Entrada desde", "Check-in instructions": "Instrucciones de entrada", "Check-in instructions (shared after booking)": "Instrucciones de entrada (se comparten tras la reserva)",
    "Check-in is only possible between %s and %s.": "La entrada solo es posible entre las %s y las %s.", "Check-in time is in the past.": "La hora de entrada ya ha pasado.",
    "Check-in until": "Entrada hasta", "Check-out": "Salida", "Check-out from": "Salida desde", "Check-out is only possible between %s and %s.": "La salida solo es posible entre las %s y las %s.",
    "Check-out must be after check-in.": "La salida debe ser posterior a la entrada.", "Check-out until": "Salida hasta", "Cleaning buffer": "Margen de limpieza", "Cover": "Portada",
    "Daily rate": "Tarifa diaria", "Daily rate ($, optional)": "Tarifa diaria ($, opcional)", "Door code, key box, floor, parking…": "Código de la puerta, caja de llaves, planta, aparcamiento…",
    "Floor": "Planta", "Free": "Libre", "Friday & Saturday": "Viernes y sábado", "Friday & Saturday hourly rate ($, optional)": "Tarifa por hora viernes y sábado ($, opcional)",
    "From date": "Desde la fecha", "Fully booked / blocked": "Completo / bloqueado", "Gross volume": "Volumen bruto", "Guest": "Huésped", "Guests": "Huéspedes",
    "Hi %s,\n\n%s booked %s.\n%s\nPayout: %s\nDetails: %s\n": "Hola %s:\n\n%s ha reservado %s.\n%s\nTu ingreso: %s\nDetalles: %s\n",
    "Hi %s,\n\n%s couldn't accept your request for %s. Your card was not charged.\nFind another apartment: %s\n": "Hola %s:\n\n%s no ha podido aceptar tu solicitud para %s. No se ha cobrado nada a tu tarjeta.\nBusca otro apartamento: %s\n",
    "Hi %s,\n\n%s requested %s.\n%s\nAccept or decline here: %s\n": "Hola %s:\n\n%s ha solicitado %s.\n%s\nAcepta o rechaza aquí: %s\n",
    "Hi %s,\n\nThe booking %s (%s) was cancelled%s.\nDetails: %s\n": "Hola %s:\n\nLa reserva %s (%s) se ha cancelado%s.\nDetalles: %s\n",
    "Hi %s,\n\nThe booking %s (%s) was cancelled%s. Refund: %s.\nDetails: %s\n": "Hola %s:\n\nLa reserva %s (%s) se ha cancelado%s. Reembolso: %s.\nDetalles: %s\n",
    "Hi %s,\n\nUse this link within 60 minutes to choose a new password:\n%s\n\nIf you didn't ask for this, ignore this email.\n": "Hola %s:\n\nUsa este enlace en los próximos 60 minutos para elegir una nueva contraseña:\n%s\n\nSi no lo has pedido tú, ignora este correo.\n",
    "Hi %s,\n\nYour %s account is ready. Browse apartments at %s\n": "Hola %s:\n\nTu cuenta de %s ya está lista. Explora apartamentos en %s\n",
    "Hi %s,\n\nYour booking is confirmed.\n%s\n%s\n%s\nDetails: %s\n": "Hola %s:\n\nTu reserva está confirmada.\n%s\n%s\n%s\nDetalles: %s\n",
    "Hi %s,\n\nYour request was sent to %s. You'll hear back soon.\n%s\nDetails: %s\n": "Hola %s:\n\nTu solicitud se ha enviado a %s. Pronto tendrás respuesta.\n%s\nDetalles: %s\n",
    "High season, Nights, Weekends…": "Temporada alta, Noches, Fines de semana…", "Host": "Anfitrión", "Host since": "Anfitrión desde", "Hourly precision": "Precisión horaria",
    "Hourly rate per day. Partially booked days still have free hours.": "Tarifa por hora de cada día. Los días parcialmente reservados aún tienen horas libres.",
    "Hours from": "Horas desde", "Hours until": "Horas hasta", "House rules": "Normas de la casa",
    "Instant confirmation on most apartments. Hosts get automatic cleaning buffers between stays.": "Confirmación inmediata en la mayoría de apartamentos. Los anfitriones tienen márgenes de limpieza automáticos entre estancias.",
    "Joined": "Alta", "Label": "Etiqueta", "Listing": "Anuncio", "Listings": "Anuncios", "Long stays": "Estancias largas", "Long-stay discount": "Descuento por estancia larga",
    "Long-stay discount (%, from 7 days)": "Descuento por estancia larga (%, a partir de 7 días)", "Make cover": "Usar de portada",
    "Manage calendar, blocked time and price rules": "Gestionar calendario, bloqueos y reglas de precio", "Max price": "Precio máx.", "Maximum stay (hours)": "Estancia máxima (horas)",
    "Maximum stay is %s hours.": "La estancia máxima es de %s horas.", "Min price": "Precio mín.", "Minimum stay (hours)": "Estancia mínima (horas)", "Minimum stay is %s hours.": "La estancia mínima es de %s horas.",
    "New booking: %s": "Nueva reserva: %s", "New message about %s": "Nuevo mensaje sobre %s", "Newest": "Más recientes",
    "No price rules yet. The base rate applies everywhere.": "Todavía no hay reglas de precio. Se aplica la tarifa base.", "No smoking, no parties, quiet after 22:00…": "No fumar, no fiestas, silencio a partir de las 22:00…",
    "Overall": "Global", "Override the hourly rate for a date range, optionally only on certain weekdays or hours of the day (e.g. nights, weekends, high season). The newest matching rule wins.":
        "Cambia la tarifa por hora en un rango de fechas, opcionalmente solo ciertos días de la semana u horas del día (p. ej. noches, fines de semana, temporada alta). Gana la regla más reciente que coincida.",
    "Partially booked": "Parcialmente reservado", "Pause": "Pausar", "Pay for the hours you use": "Paga por las horas que usas", "Phone": "Teléfono", "Photos": "Fotos",
    "Platform revenue": "Ingresos de la plataforma", "Price rules": "Reglas de precio", "Price: high to low": "Precio: de mayor a menor", "Price: low to high": "Precio: de menor a mayor",
    "Prices are per hour, with daily rates applied automatically on longer stays. No nightly minimums, no fixed check-in times.": "Los precios son por hora, y en estancias largas se aplica automáticamente la tarifa diaria. Sin mínimo de noches ni horas de entrada fijas.",
    "Pricing": "Precios", "Profile photo": "Foto de perfil", "Rate": "Tarifa", "Recommended": "Recomendados", "Reinstate": "Reactivar", "Reply": "Responder",
    "Request declined: %s": "Solicitud rechazada: %s", "Request sent: %s": "Solicitud enviada: %s", "Reset your %s password": "Restablece tu contraseña de %s", "Response from": "Respuesta de",
    "Review this guest": "Valorar a este huésped", "Reviews as a guest": "Reseñas como huésped", "Reviews as a host": "Reseñas como anfitrión", "Role": "Rol", "Rule": "Regla",
    "Save": "Guardar", "Saved": "Guardados", "Saved apartments": "Apartamentos guardados", "Seasonal and per-hour price rules are managed from the calendar after publishing.": "Las reglas de precio por temporada y por horas se gestionan desde el calendario una vez publicado.",
    "Show all %s photos": "Ver las %s fotos", "Shown on your public profile": "Se muestra en tu perfil público", "Size (m²)": "Superficie (m²)", "Stay": "Estancia", "Stay details": "Detalles de la estancia",
    "Stay length": "Duración", "Stay two hours or two weeks.": "Quédate dos horas o dos semanas.", "Suspend": "Suspender",
    "Tell us where, from when and until when. We only show apartments that are free for your whole stay.": "Dinos dónde, desde cuándo y hasta cuándo. Solo mostramos apartamentos libres durante toda tu estancia.",
    "This host needs %s hours' notice before check-in.": "Este anfitrión necesita %s horas de antelación antes de la entrada.", "Times must be on the hour.": "Las horas deben ser en punto.",
    "To date": "Hasta la fecha", "Users": "Usuarios", "View": "Ver", "View public profile": "Ver perfil público", "Welcome to %s": "Bienvenido a %s",
    "What makes it great, what is nearby, what a guest should know.": "Qué lo hace especial, qué hay cerca, qué debería saber un huésped.", "Write a public response…": "Escribe una respuesta pública…",
    "You haven't saved any apartments yet.": "Todavía no has guardado ningún apartamento.", "active": "activo", "available from": "disponibles desde", "base rate": "tarifa base",
    "cap per 24h": "tope por 24 h", "check in and out at any hour; pay only for the hours you use.": "entra y sal a cualquier hora; paga solo por las horas que usas.", "day": "día", "days": "días",
    "ground": "baja", "hosts": "anfitriones", "is yours from": "es tuyo desde", "min between stays": "min entre estancias", "off from 7 days": "de descuento a partir de 7 días",
    "per 24h (applied automatically when cheaper)": "por 24 h (se aplica automáticamente cuando sale más barato)", "suspended": "suspendido", "Available": "Disponible",
    "Checking availability…": "Comprobando disponibilidad…", "paused": "pausado", "flexible": "flexible", "moderate": "moderada", "strict": "estricta",
    "policy_flexible": "reembolso total hasta 24 h antes de la entrada", "policy_moderate": "reembolso total hasta 5 días antes, 50 % hasta 24 h antes",
    "policy_strict": "reembolso total hasta 14 días antes, 50 % hasta 7 días antes", "tab_overview": "Resumen", "tab_users": "Usuarios", "tab_listings": "Anuncios", "tab_bookings": "Reservas",
    "cleanliness": "limpieza", "accuracy": "veracidad", "communication": "comunicación", "location": "ubicación", "value": "calidad-precio",
    "This account has been suspended.": "Esta cuenta ha sido suspendida.", "Admin access required.": "Se necesita acceso de administrador.", "User not found.": "Usuario no encontrado.",
    "Review not found.": "Reseña no encontrada.", "You can only review a guest after a completed stay, once.": "Solo puedes valorar a un huésped tras una estancia completada, y una sola vez.",
    "Photo is too large (max 12 MB).": "La foto es demasiado grande (máx. 12 MB).", "That file is not an image.": "Ese archivo no es una imagen.", "Photo limit reached.": "Has llegado al límite de fotos.",
    "The daily rate should not exceed 24 times the hourly rate.": "La tarifa diaria no debería superar 24 veces la tarifa por hora.", "Check the minimum / maximum stay.": "Revisa la estancia mínima / máxima.",
    "Check-in / check-out hours must be on the hour.": "Las horas de entrada / salida deben ser en punto.",
})

ES.update({
    "Whatever the moment, there is an apartment for it": "Sea cual sea el momento, hay un apartamento para él",
    "Between flights": "Entre vuelos", "A shower, a nap and a desk, three blocks from the terminal.": "Una ducha, una siesta y un escritorio, a tres calles de la terminal.",
    "A night out, a place to land": "Una noche fuera, un sitio donde caer", "Book from 23:00 to 11:00 and pay for exactly that.": "Reserva de 23:00 a 11:00 y paga exactamente eso.",
    "A working week": "Una semana de trabajo", "Check in Monday at 8, out Friday at 19. Daily rates apply automatically.": "Entra el lunes a las 8, sal el viernes a las 19. La tarifa diaria se aplica sola.",
    "A celebration": "Una celebración", "Big flats by the hour for birthdays, showers and dinners.": "Pisos grandes por horas para cumpleaños, baby showers y cenas.",
    "Your apartment earns while you are out": "Tu apartamento genera ingresos mientras no estás",
    "List it once, set your hourly and daily rates, block the hours you need, and let guests book the rest. Cleaning buffers, calendar rules and payouts are handled for you.":
        "Publícalo una vez, fija tu tarifa por hora y por día, bloquea las horas que necesites y deja que los huéspedes reserven el resto. Los márgenes de limpieza, las reglas del calendario y los pagos van por nuestra cuenta.",
    "See a host profile": "Ver el perfil de un anfitrión", "Your time, your hours, your place.": "Tu tiempo, tus horas, tu lugar.",
})

ES["Check in and out at any hour and pay only for the time you use."] = "Entra y sal a cualquier hora y paga solo por el tiempo que usas."

ES.update({
    "High-speed Wi-Fi (1 Gbps)": "Wi-Fi de alta velocidad (1 Gbps)", "Ceiling fan": "Ventilador de techo", "Smart TV": "Smart TV", "Netflix": "Netflix",
    "Prime Video": "Prime Video", "HBO": "HBO", "YouTube Premium": "YouTube Premium", "Kitchenette": "Cocineta", "Microwave": "Microondas",
    "Refrigerator": "Refrigerador", "Mini fridge": "Mini refri", "Coffee maker": "Cafetera", "Kettle": "Hervidor", "Queen bed": "Cama Queen",
    "Full bed": "Cama matrimonial", "2 Queen beds": "2 camas Queen", "Desk": "Escritorio", "Closet": "Clóset", "Private bathroom": "Baño privado",
    "Clothes dryer": "Secadora de ropa", "Parking with electric gate": "Estacionamiento con portón eléctrico", "Private pool": "Alberca privada",
    "BBQ grill": "Asador", "Toiletries included": "Jabones incluidos", "No deposit": "Sin depósito", "No guarantor": "Sin aval",
    "two_days": "2 días", "policy_two_days": "reembolso total hasta 2 días antes, 50 % hasta 1 día antes",
    "Monthly rate ($, optional)": "Tarifa mensual ($, opcional)", "Guests included in the price": "Huéspedes incluidos en el precio",
    "Extra guest fee ($, per day)": "Cargo por huésped extra ($, por día)", "Extra guests": "Huéspedes extra", "month": "mes", "months": "meses",
    "Monthly rate": "Tarifa mensual", "per 30 days": "por 30 días", "Extra guest": "Huésped extra", "per day beyond": "por día a partir de",
    "WhatsApp": "WhatsApp", "Chat on WhatsApp": "Escríbenos por WhatsApp", "Questions? Chat with us on WhatsApp.": "¿Dudas? Escríbenos por WhatsApp.",
    "guests included": "huéspedes incluidos",
})
ES.update({"Founder & owner": "Fundador y propietario", "Hola, me interesa": "Hola, me interesa",
    "Furnished, fully equipped apartments in Mérida and on the beach in Chicxulub Puerto. No deposit, no guarantor, no hassle. Every apartment has a Smart TV with Netflix, fast Wi-Fi, air conditioning, pool and parking.":
    "Departamentos amueblados y equipados en Mérida y en la playa de Chicxulub Puerto. Sin depósito, sin aval, sin complicaciones. Todos tienen Smart TV con Netflix, Wi-Fi rápido, aire acondicionado, alberca y estacionamiento.",
    "Netflix included": "Netflix incluido", "Our apartments": "Nuestros departamentos", "Pick a check-in and check-out and search to see availability.": "Elige entrada y salida y busca para ver la disponibilidad.", "all": "todos", "cap per 30 days": "tope por 30 días", "/ month": "/ mes", "Price per day for the minimum stay. Partially booked days still have free hours.": "Precio por día para la estancia mínima. Los días parcialmente reservados aún tienen horas libres."})
EN_LABELS.update({"policy_two_days": "full refund until 2 days before check-in, 50% until 1 day before", "two_days": "2 days"})

CATALOG = {"es": ES}
