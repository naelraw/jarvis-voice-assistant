// Script Google Apps Script : permet à JARVIS de lire, ajouter et supprimer des rendez-vous
// dans TON Google Agenda. Protégé par un code secret (TOKEN) connu seulement de ton PC.
const TOKEN = '__TOKEN__';

function doPost(e) {
  let req;
  try { req = JSON.parse(e.postData.contents); } catch (err) { return out({ ok: false, error: 'requête illisible' }); }
  if (req.token !== TOKEN) return out({ ok: false, error: 'code secret incorrect' });
  const cal = CalendarApp.getDefaultCalendar();

  if (req.action === 'list') {
    const events = cal.getEvents(new Date(req.start), new Date(req.end)).map(ev => ({
      id: ev.getId(), title: ev.getTitle(), start: ev.getStartTime().toISOString(),
      end: ev.getEndTime().toISOString(), allDay: ev.isAllDayEvent(), location: ev.getLocation(),
    }));
    return out({ ok: true, events });
  }
  if (req.action === 'add') {
    const opts = { description: req.details || '', location: req.location || '' };
    const ev = req.allDay
      ? cal.createAllDayEvent(req.title, new Date(req.start), opts)
      : cal.createEvent(req.title, new Date(req.start), new Date(req.end), opts);
    if (req.reminderMinutes) ev.addPopupReminder(req.reminderMinutes);
    return out({ ok: true, id: ev.getId() });
  }
  if (req.action === 'delete') {
    const ev = cal.getEventById(req.id);
    if (!ev) return out({ ok: false, error: 'rendez-vous introuvable' });
    ev.deleteEvent();
    return out({ ok: true });
  }
  return out({ ok: false, error: 'action inconnue' });
}

function out(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
