"""
Inspection session management: directory layout, evidence photos, findings log, PDF report.
"""

import json
from datetime import datetime
from pathlib import Path

import cv2


class Session:
    """
    Owns one inspection session's on-disk state.

    Directory layout:
        sessions/<YYYYMMDD_HHMMSS>/
            session.json        unit metadata + start/end times
            findings.jsonl      one JSON finding per line, appended live
            evidence/           JPEG snapshots saved during inspection
            report.json         AI-generated final report (written on close)
            report.pdf          rendered PDF (optional, requires fpdf2)
    """

    def __init__(self, unit_info):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.dir          = Path("sessions") / ts
        self.evidence_dir = self.dir / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.unit_info    = unit_info
        self.start_time   = datetime.now()
        self._findings_fh = open(self.dir / "findings.jsonl", "a")
        self._evi_count   = 0
        (self.dir / "session.json").write_text(
            json.dumps({"unit": unit_info, "start_time": self.start_time.isoformat()}, indent=2)
        )

    def save_evidence(self, frame, label="manual"):
        self._evi_count += 1
        fname = f"{datetime.now().strftime('%H%M%S')}_{self._evi_count:04d}_{label}.jpg"
        cv2.imwrite(str(self.evidence_dir / fname), frame)
        return fname

    def log_finding(self, finding):
        finding["timestamp"] = datetime.now().isoformat()
        self._findings_fh.write(json.dumps(finding) + "\n")
        self._findings_fh.flush()

    def save_report(self, report_data):
        text = json.dumps(report_data, indent=2) if isinstance(report_data, dict) else str(report_data)
        (self.dir / "report.json").write_text(text)

    def generate_pdf(self, findings, report_json, coverage_pct):
        try:
            from fpdf import FPDF
        except ImportError:
            print("  fpdf2 not installed, skipping PDF.")
            return None

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        self._pdf_header(pdf, coverage_pct)
        self._pdf_findings(pdf, findings)
        self._pdf_evidence_photos(pdf)
        self._pdf_ai_summary(pdf, report_json)

        pdf_path = self.dir / "report.pdf"
        pdf.output(str(pdf_path))
        return str(pdf_path)

    def close(self, coverage_pct):
        meta = json.loads((self.dir / "session.json").read_text())
        meta.update({
            "end_time":      datetime.now().isoformat(),
            "duration_s":    (datetime.now() - self.start_time).total_seconds(),
            "coverage_pct":  round(coverage_pct, 1),
            "evidence_count": self._evi_count,
        })
        (self.dir / "session.json").write_text(json.dumps(meta, indent=2))
        self._findings_fh.close()

    # ── PDF helpers ──────────────────────────────────────────────────────────

    def _pdf_header(self, pdf, coverage_pct):
        u   = self.unit_info
        dur = (datetime.now() - self.start_time).total_seconds() / 60
        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 12, "CAT 325 Daily Walk-Around Inspection", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Unit: {u.get('model','')} | Serial: {u.get('serial','')} | {u.get('hours',0)}h",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Date: {self.start_time.strftime('%Y-%m-%d %H:%M')} | Coverage: {coverage_pct:.0f}%",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Duration: {dur:.1f} min | Evidence: {self._evi_count} photos",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)

    def _pdf_findings(self, pdf, findings):
        sev_colors = {"RED": (200, 0, 0), "YELLOW": (180, 140, 0), "GREEN": (0, 130, 0)}
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, "Zone Findings", new_x="LMARGIN", new_y="NEXT")
        for f in findings:
            r, g, b = sev_colors.get(f.get("rating", "GREEN"), (0, 0, 0))
            pdf.set_text_color(r, g, b)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(30, 6, f"[{f.get('rating','GREEN')}]")
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 6, f"{f.get('zone','unknown')}: {f.get('description','')[:120]}")
            pdf.ln(1)

    def _pdf_evidence_photos(self, pdf):
        evi_files = sorted(self.evidence_dir.glob("*.jpg"))
        if not evi_files:
            return
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, "Evidence Photos", new_x="LMARGIN", new_y="NEXT")
        for img_path in evi_files[:12]:
            try:
                if pdf.get_y() > 230:
                    pdf.add_page()
                pdf.set_font("Helvetica", "", 8)
                pdf.cell(0, 4, img_path.name, new_x="LMARGIN", new_y="NEXT")
                pdf.image(str(img_path), w=80)
                pdf.ln(3)
            except Exception:
                pass

    def _pdf_ai_summary(self, pdf, report_json):
        if not report_json:
            return
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, "AI Executive Summary", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        summary = (
            report_json.get("ai_executive_summary", json.dumps(report_json, indent=2))
            if isinstance(report_json, dict) else str(report_json)
        )
        pdf.multi_cell(0, 5, summary[:2000])
