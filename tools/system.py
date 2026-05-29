import psutil
import platform

TOOLS = [{"name": "system_info", "description": "Stato PC: CPU, RAM, disco, batteria, processi.",
    "input_schema": {"type": "object", "properties": {"detail": {"type": "string", "enum": ["summary", "processes", "battery"]}}}}]


def run(name, args):
    detail = args.get("detail", "summary")
    if detail == "processes":
        procs = []
        for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except Exception:
                pass
        procs.sort(key=lambda x: x.get("cpu_percent", 0) or 0, reverse=True)
        top = procs[:10]
        lines = [f"{p['name']}: CPU {p.get('cpu_percent', 0):.1f}%, RAM {p.get('memory_percent', 0):.1f}%" for p in top]
        return "Top 10 processi per CPU:\n" + "\n".join(lines)

    if detail == "battery":
        b = psutil.sensors_battery()
        if not b:
            return "Nessuna batteria rilevata (desktop?)."
        plug = "in carica" if b.power_plugged else "scollegata"
        return f"Batteria: {b.percent:.0f}% ({plug})"

    cpu = psutil.cpu_percent(interval=0.3)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")
    return (f"Sistema: {platform.system()} {platform.release()}\n"
            f"CPU: {cpu:.1f}% su {psutil.cpu_count()} core\n"
            f"RAM: {ram.percent}% usato ({ram.used/1e9:.1f}/{ram.total/1e9:.1f} GB)\n"
            f"Disco C: {disk.percent}% usato ({disk.used/1e9:.0f}/{disk.total/1e9:.0f} GB)")
