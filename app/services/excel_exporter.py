"""Write hotel search results and request details to an Excel workbook."""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from app.models import HotelOffer, SearchRequest

_HEADER_FILL = PatternFill("solid", fgColor="282326")
_HEADER_FONT = Font(color="FBF9F3", bold=True)


def export_offers_to_excel(
    offers: list[HotelOffer],
    request: SearchRequest,
    output_path: str | Path,
) -> Path:
    """Save all matching hotel offers to an ``.xlsx`` workbook."""
    path = Path(output_path)
    if path.suffix.lower() != ".xlsx":
        raise ValueError("The Excel report path must end with .xlsx.")

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    offers_sheet = workbook.active
    offers_sheet.title = "Hotel offers"
    offers_sheet.append(
        [
            "Hotel",
            "Amount per night",
            "Total amount",
            "Currency",
            "Guest rating",
            "Address",
            "Latitude",
            "Longitude",
        ]
    )

    nights = (request.check_out - request.check_in).days
    for offer in offers:
        offers_sheet.append(
            [
                offer.hotel_name,
                offer.nightly_price,
                round(offer.nightly_price * nights, 2),
                offer.currency,
                offer.guest_rating or None,
                offer.address,
                offer.latitude,
                offer.longitude,
            ]
        )

    _format_header(offers_sheet)
    offers_sheet.freeze_panes = "A2"
    offers_sheet.auto_filter.ref = f"A1:H{max(1, offers_sheet.max_row)}"
    offers_sheet.column_dimensions["A"].width = 34
    offers_sheet.column_dimensions["B"].width = 20
    offers_sheet.column_dimensions["C"].width = 20
    offers_sheet.column_dimensions["D"].width = 12
    offers_sheet.column_dimensions["E"].width = 15
    offers_sheet.column_dimensions["F"].width = 44
    offers_sheet.column_dimensions["G"].width = 14
    offers_sheet.column_dimensions["H"].width = 14
    for row in offers_sheet.iter_rows(min_row=2):
        row[1].number_format = "#,##0.00"
        row[2].number_format = "#,##0.00"
        row[4].number_format = "0.0"
        row[5].alignment = Alignment(wrap_text=True, vertical="top")
        row[6].number_format = "0.000000"
        row[7].number_format = "0.000000"

    workbook.save(path)
    return path


def _format_header(sheet: Worksheet) -> None:
    for cell in sheet[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    sheet.row_dimensions[1].height = 24
