"""ponytail: one worker function for both PDF and CSV export — they share
the same data-fetch step and only differ in the final render call.
Splitting into report_worker_pdf.py / report_worker_csv.py would just be
two files importing the same query logic."""


async def generate_report(ctx, workspace_id: str, report_type: str, format: str) -> dict:
    # ponytail: actual rendering (WeasyPrint for PDF, stdlib csv for CSV)
    # stubbed until reporting/router.py's aggregation queries are real.
    raise NotImplementedError
