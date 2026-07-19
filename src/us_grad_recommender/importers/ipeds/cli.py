from __future__ import annotations

import argparse
import sys
from datetime import date

from us_grad_recommender.db import get_session
from us_grad_recommender.importers.ipeds.ef_importer import import_ef_file, read_ef_rows
from us_grad_recommender.importers.ipeds.hd_importer import import_hd_file, read_hd_rows


def _run_hd(args: argparse.Namespace) -> int:
    session = get_session()
    try:
        with open(args.file, encoding="utf-8-sig", newline="") as f:
            summary = import_hd_file(
                session,
                read_hd_rows(f),
                ipeds_year=args.year,
                masters_only=not args.include_all,
                run_date=date.today(),
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"HD{args.year} import complete:")
    print(f"  rows read:                         {summary.rows_read}")
    print(f"  universities upserted:              {summary.universities_upserted}")
    print(f"  aliases upserted:                   {summary.aliases_upserted}")
    not_masters = summary.universities_skipped_not_masters_granting
    print(f"  skipped (not master's-granting):    {not_masters}")
    print(f"  skipped (invalid row):              {summary.universities_skipped_invalid}")
    if summary.issues:
        print("  first invalid rows:")
        for issue in summary.issues[:10]:
            print(f"    line {issue.line_number} (UNITID={issue.unitid_raw!r}): {issue.reason}")
    return 0


def _run_ef(args: argparse.Namespace) -> int:
    session = get_session()
    try:
        with open(args.file, encoding="utf-8-sig", newline="") as f:
            summary = import_ef_file(session, read_ef_rows(f), ef_year=args.year)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"EF{args.year}A import complete:")
    print(f"  rows read:                         {summary.rows_read}")
    print(f"  institutions updated:               {summary.institutions_updated}")
    print(f"  skipped (institution not indexed):  {summary.institutions_skipped_not_found}")
    if summary.skipped_unitids:
        preview = ", ".join(str(u) for u in summary.skipped_unitids[:10])
        print(f"    e.g. UNITIDs: {preview}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="import-ipeds",
        description="Idempotent importers for IPEDS institutional data.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    hd_parser = subparsers.add_parser(
        "hd", help="Import an IPEDS HD (institutional characteristics) file."
    )
    hd_parser.add_argument("--file", required=True, help="Path to hd<year>.csv")
    hd_parser.add_argument("--year", required=True, type=int, help="IPEDS release year, e.g. 2023")
    hd_parser.add_argument(
        "--include-all",
        action="store_true",
        help="Import every institution in the file, not only master's-granting ones.",
    )
    hd_parser.set_defaults(func=_run_hd)

    ef_parser = subparsers.add_parser(
        "ef", help="Import an IPEDS EF (fall enrollment), component A file."
    )
    ef_parser.add_argument("--file", required=True, help="Path to ef<year>a.csv")
    ef_parser.add_argument("--year", required=True, type=int, help="IPEDS release year, e.g. 2023")
    ef_parser.set_defaults(func=_run_ef)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
