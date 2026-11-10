import io
import json
import uuid
from datetime import timedelta
from django.contrib import messages

import qrcode
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import VisitorForm
from .models import Blacklist, Logbook, Notification, Visitor, VisitorPass


def _active_passes():
    """Passes still in use: inside now, or registered in the last 12 hours but not scanned yet."""
    recent = timezone.now() - timedelta(hours=12)
    return VisitorPass.objects.filter(
        Q(logbook__status="Ongoing") | Q(logbook__status="Pending", issued_at__gte=recent)
    )


def register(request):
    # Layer A: does this phone already have an active pass? (remembered in the browser session)
    active_pass = None
    saved = request.session.get("active_pass")
    if saved:
        active_pass = _active_passes().filter(token=saved).first()

    if request.method == "POST":
        form = VisitorForm(request.POST)
        if form.is_valid():
            plate = form.cleaned_data["vehicle_plate"]
            ic = form.cleaned_data["ic_number"]

            # Reject if plate or IC is on the blacklist
            is_blacklisted = Blacklist.objects.filter(
                Q(vehicle_plate__iexact=plate) | Q(ic_number=ic)
            ).exists()
            if is_blacklisted:
                return render(request, "visitors/blacklisted.html")

            # Layer B: same plate and IC already has an active visit, so give back that pass
            existing = (
                _active_passes()
                .filter(visitor__vehicle_plate__iexact=plate, visitor__ic_number=ic)
                .order_by("-issued_at")
                .first()
            )
            if existing:
                request.session["active_pass"] = str(existing.token)
                messages.info(request, "You already have an active visit, so here is your existing pass.")
                return redirect("visitor_pass", token=existing.token)

            visitor = form.save()
            vpass = VisitorPass.objects.create(visitor=visitor)
            Logbook.objects.create(visitor_pass=vpass)  # status starts as Pending
            request.session["active_pass"] = str(vpass.token)
            return redirect("visitor_pass", token=vpass.token)
    else:
        form = VisitorForm()
    return render(request, "visitors/register.html", {"form": form, "active_pass": active_pass})

def visitor_pass(request, token):
    vpass = get_object_or_404(VisitorPass, token=token)
    log = Logbook.objects.filter(visitor_pass=vpass).first()
    return render(request, "visitors/pass.html", {"vpass": vpass, "log": log})


@require_POST
def leave(request, token):
    vpass = get_object_or_404(VisitorPass, token=token)
    log = Logbook.objects.filter(visitor_pass=vpass).first()
    if log and log.status == "Ongoing":
        log.exit_time = timezone.now()
        log.status = "Completed"
        log.exit_method = "visitor"
        log.save()
    return redirect("visitor_pass", token=token)


def pass_qr(request, token):
    vpass = get_object_or_404(VisitorPass, token=token)
    image = qrcode.make(str(vpass.token))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return HttpResponse(buffer.getvalue(), content_type="image/png")

@login_required
def scanner(request):
    return render(request, "visitors/scanner.html")


@login_required
@require_POST
def scan_api(request):
    # 1. Read the token sent by the scanner page
    try:
        data = json.loads(request.body)
        token = uuid.UUID(str(data.get("token", "")).strip())
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "code": "invalid"}, status=400)

    # 2. Find the pass
    vpass = VisitorPass.objects.filter(token=token).select_related("visitor").first()
    if vpass is None:
        return JsonResponse({"ok": False, "code": "not_found"}, status=404)

    visitor = vpass.visitor
    info = {"name": visitor.name, "plate": visitor.vehicle_plate, "phone": visitor.phone}
    log = Logbook.objects.filter(visitor_pass=vpass).first()

    # 3. New pass: check the blacklist, then record entry
    if log.status == "Pending":
        blacklisted = Blacklist.objects.filter(
            Q(vehicle_plate__iexact=visitor.vehicle_plate) | Q(ic_number=visitor.ic_number)
        ).exists()
        if blacklisted:
            return JsonResponse({"ok": False, "code": "blacklisted", **info})
        log.entry_time = timezone.now()
        log.status = "Ongoing"
        log.save()
        return JsonResponse(
            {"ok": True, "code": "entry", "limit": vpass.time_limit_minutes, **info}
        )

    # 4. Already inside: show info only, never record an exit from a scan
    if log.status == "Ongoing":
        return JsonResponse({
            "ok": True,
            "code": "inside",
            "entered": timezone.localtime(log.entry_time).strftime("%H:%M"),
            "left": vpass.time_limit_minutes - log.elapsed_minutes(),
            **info,
        })

    # 5. Visit finished: the pass can't be reused
    return JsonResponse({"ok": False, "code": "used", **info})

def _tel(phone):
    """Turn 012-345 6789 into +60123456789 so the phone can dial it."""
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("0"):
        digits = "6" + digits
    return "+" + digits


def _mask_ic(ic):
    """960110101234 -> 96****-10-**** (same style as your mockup)."""
    if len(ic) == 12 and ic.isdigit():
        return f"{ic[:2]}****-{ic[6:8]}-****"
    return "****"


def _row(log):
    v = log.visitor_pass.visitor
    entry = log.entry_time
    return {
        "id": log.id,
        "name": v.name,
        "plate": v.vehicle_plate,
        "phone": v.phone,
        "tel": _tel(v.phone),
        "entry": timezone.localtime(entry).strftime("%H:%M") if entry else "-",
        "entry_ts": entry.timestamp() if entry else 0,
        "limit": log.visitor_pass.time_limit_minutes,
    }


def _is_over(log):
    deadline = log.entry_time + timedelta(minutes=log.visitor_pass.time_limit_minutes)
    return timezone.now() > deadline


@login_required
def dashboard(request):
    return render(request, "visitors/dashboard.html")


@login_required
def dashboard_data(request):
    # Ongoing visitors. The browser counts the seconds itself, so we only
    # send the entry timestamp and the limit.
    logs = Logbook.objects.filter(
        status="Ongoing", entry_time__isnull=False
    ).select_related("visitor_pass__visitor")
    ongoing = []
    for log in logs:
        row = _row(log)
        if _is_over(log) and not log.notification_set.exists():
            Notification.objects.create(
                logbook=log,
                message=f"{row['name']} ({row['plate']}) has overstayed the {row['limit']}-minute limit.",
            )
        row["deadline"] = row["entry_ts"] + row["limit"] * 60
        ongoing.append(row)
    ongoing.sort(key=lambda r: r["deadline"])  # closest to overstaying first

    # Last 20 completed visits
    done = (
        Logbook.objects.filter(status="Completed")
        .select_related("visitor_pass__visitor")
        .order_by("-exit_time")[:20]
    )
    completed = []
    for log in done:
        row = _row(log)
        row["exit"] = timezone.localtime(log.exit_time).strftime("%H:%M")
        row["method"] = log.exit_method or "-"
        row["stayed"] = log.elapsed_minutes()
        completed.append(row)

    # Unread overstay alerts
    alerts = []
    unread = (
        Notification.objects.filter(is_read=False)
        .select_related("logbook__visitor_pass__visitor")
        .order_by("-created_at")
    )
    for n in unread:
        vp = n.logbook.visitor_pass
        v = vp.visitor
        alerts.append({
            "id": n.id,
            "name": v.name,
            "plate": v.vehicle_plate,
            "phone": v.phone,
            "tel": _tel(v.phone),
            "limit": vp.time_limit_minutes,
        })

    # Blacklist, and which visitors match it
    entries = list(Blacklist.objects.order_by("-blacklisted_at"))
    bl_plates = {b.vehicle_plate.upper() for b in entries if b.vehicle_plate}
    bl_ics = {b.ic_number for b in entries if b.ic_number}

    # Older entries have no saved name, so look it up from the visitor records
    known = list(Visitor.objects.order_by("created_at"))
    name_by_plate = {v.vehicle_plate.upper(): v.name for v in known}
    name_by_ic = {v.ic_number: v.name for v in known}

    blacklist = [
        {
            "id": b.id,
            "name": b.name
            or name_by_plate.get(b.vehicle_plate.upper())
            or name_by_ic.get(b.ic_number)
            or "-",
            "who": " / ".join(
                x for x in [b.vehicle_plate, _mask_ic(b.ic_number) if b.ic_number else ""] if x
            ),
            "reason": b.reason,
            "date": timezone.localtime(b.blacklisted_at).strftime("%d %b %Y"),
            "by": b.added_by or "-",
        }
        for b in entries
    ]

    # Latest 100 different visitors (the same person may have registered many times)
    visitors, seen = [], set()
    for v in Visitor.objects.order_by("-created_at")[:300]:
        key = (v.vehicle_plate, v.ic_number)
        if key in seen:
            continue
        seen.add(key)
        visitors.append({
            "id": v.id,
            "name": v.name,
            "plate": v.vehicle_plate,
            "phone": v.phone,
            "ic": _mask_ic(v.ic_number),
            "blacklisted": v.vehicle_plate.upper() in bl_plates or v.ic_number in bl_ics,
        })
        if len(visitors) >= 100:
            break

    return JsonResponse({
        "server_now": timezone.now().timestamp(),
        "can_blacklist": request.user.is_staff,
        "ongoing": ongoing,
        "completed": completed,
        "alerts": alerts,
        "visitors": visitors,
        "blacklist": blacklist,
    })


@login_required
@require_POST
def mark_exited(request, pk):
    log = get_object_or_404(Logbook, pk=pk, status="Ongoing")
    log.exit_time = timezone.now()
    log.status = "Completed"
    log.exit_method = "staff"
    log.save()
    log.notification_set.update(is_read=True)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def extend_stay(request, pk):
    log = get_object_or_404(Logbook, pk=pk, status="Ongoing")
    vpass = log.visitor_pass
    vpass.time_limit_minutes = max(vpass.time_limit_minutes, log.elapsed_minutes()) + 15
    vpass.save()
    log.notification_set.all().delete()  # clear the old alert so a new one can fire later
    return JsonResponse({"ok": True})


@login_required
@require_POST
def dismiss_notification(request, pk):
    Notification.objects.filter(pk=pk).update(is_read=True)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def blacklist_visitor(request, pk):
    if not request.user.is_staff:
        return JsonResponse({"ok": False, "message": "Admins only."}, status=403)
    visitor = get_object_or_404(Visitor, pk=pk)
    try:
        reason = str(json.loads(request.body).get("reason", "")).strip()
    except (ValueError, AttributeError):
        reason = ""
    if not reason:
        return JsonResponse({"ok": False, "message": "A reason is required."}, status=400)
    Blacklist.objects.create(
        name=visitor.name,
        vehicle_plate=visitor.vehicle_plate,
        ic_number=visitor.ic_number,
        reason=reason[:255],
        added_by=request.user.username,
    )
    return JsonResponse({"ok": True})


@login_required
@require_POST
def remove_blacklist(request, pk):
    if not request.user.is_staff:
        return JsonResponse({"ok": False, "message": "Admins only."}, status=403)
    Blacklist.objects.filter(pk=pk).delete()
    return JsonResponse({"ok": True})