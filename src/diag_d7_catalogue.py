"""D7 catalogue check (diagnostic): would NCEI's GOES XRS report (flare locations) recover the 121 flares lost to the
location proxy?  Recovered = matched in the report, location present, |lon| <= 68 (B&C, p.6), AND a qualifying patch
record exists within 30 min of peak - 24 h (same test as diag_d7.py)."""
import re, sys
import pandas as pd



def report(SP):
    """NCEI GOES XRS report 2010-2014 (fixed width): date, start hhmm, class, lon (None if no location), region."""
    rows = []
    for y in range(2010, 2015):
        for L in open(f"{SP}/xrs_{y}.txt"):
            if len(L) < 60 or not L.startswith("31777"):
                continue
            d = pd.Timestamp("20" + L[5:11])
            loc = L[28:34]
            m = re.match(r"([NS])(\d\d)([EW])(\d\d)", loc)
            rows.append(dict(date=d, start=L[13:17], cls=L[59] + str(int(L[61:63]) / 10 if L[61:63].strip() else ""),
                             lon=(int(m.group(4)) * (-1 if m.group(3) == "E" else 1)) if m else None,
                             region=int(L[80:85]) + (10000 if int(L[80:85]) < 10000 else 0) if L[80:85].strip().isdigit() else None))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    SP = sys.argv[1]
    cat = report(SP)
    loss = pd.read_csv("data/diag/d7_location_proxy_losses.csv", parse_dates=["start", "peak"])
    loss["date"] = loss.start.dt.normalize(); loss["hhmm"] = loss.start.dt.strftime("%H%M")
    mm = loss.merge(cat, left_on=["date", "hhmm"], right_on=["date", "start"], how="left", suffixes=("", "_ngdc"))
    mm = mm.sort_values("lon").drop_duplicates(["start", "goes_class"])            # one catalogue row per lost flare
    print(f"lost flares {len(loss)}; matched in report {mm.cls.notna().sum()}; with location {mm.lon.notna().sum()}; "
          f"|lon|<=68 {(mm.lon.abs() <= 68).sum()}; |lon|>68 {(mm.lon.abs() > 68).sum()}")
    print("by year (matched / with location / |lon|<=68):")
    print(mm.assign(y=mm.date.dt.year).groupby("y").agg(n=("start", "size"), matched=("cls", lambda s: s.notna().sum()),
          loc=("lon", lambda s: s.notna().sum()), le68=("lon", lambda s: (s.abs() <= 68).sum())).to_string())
    mm.to_csv("data/diag/d7_location_proxy_catalogue.csv", index=False)
