import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError
from api.models import School, ExamResult
import re
import os

BASE_URL = "https://onlinesys.necta.go.tz/results/{year}/{exam}/"

class Command(BaseCommand):
    help = "Scrape NECTA results for CSEE or ACSEE and rank schools"

    def add_arguments(self, parser):
        parser.add_argument("--exam", type=str, required=True, help="Exam type: CSEE or ACSEE")
        parser.add_argument("--year", type=int, required=True, help="Exam year (e.g. 2023)")

    def parse_division_summary(self, soup):
        div_counts = {"I": 0, "II": 0, "III": 0, "IV": 0, "0": 0}
        division_table = None
        tables = soup.find_all('table')
        for table in tables:
            if 'DIVISION PERFORMANCE SUMMARY' in table.get_text():
                division_table = table
                break
        
        if division_table:
            rows = division_table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 6 and cells[0].get_text(strip=True).upper() == 'T':
                    try:
                        div_counts["I"] = int(cells[1].get_text(strip=True) or 0)
                        div_counts["II"] = int(cells[2].get_text(strip=True) or 0)
                        div_counts["III"] = int(cells[3].get_text(strip=True) or 0)
                        div_counts["IV"] = int(cells[4].get_text(strip=True) or 0)
                        div_counts["0"] = int(cells[5].get_text(strip=True) or 0)
                    except ValueError:
                        pass
                    break
        
        if not any(div_counts.values()):
            text = soup.get_text()
            patterns = [
                r'[Tt]\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',
                r'Total\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',
            ]
            for pattern in patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    if len(match) == 5:
                        try:
                            div_counts["I"] = int(match[0])
                            div_counts["II"] = int(match[1])
                            div_counts["III"] = int(match[2])
                            div_counts["IV"] = int(match[3])
                            div_counts["0"] = int(match[4])
                            break
                        except ValueError:
                            pass
        
        return div_counts

    def parse_overall_performance(self, soup):
        overall = {}
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 2:
                    key = cells[0].get_text(strip=True).upper()
                    value = cells[1].get_text(strip=True)
                    overall[key] = value
        return overall

    def parse_division_performance(self, soup):
        division_perf = {}
        tables = soup.find_all('table')
        for table in tables:
            if 'EXAMINATION CENTRE DIVISION PERFORMANCE' in table.get_text():
                rows = table.find_all('tr')
                if len(rows) > 1:
                    headers = [cell.get_text(strip=True) for cell in rows[0].find_all('td')]
                    values = [cell.get_text(strip=True) for cell in rows[1].find_all('td')]
                    for h, v in zip(headers, values):
                        division_perf[h] = v
                break
        return division_perf

    def parse_subjects_performance(self, soup):
        subjects = []
        tables = soup.find_all('table')
        for table in tables:
            if 'EXAMINATION CENTRE SUBJECTS PERFORMANCE' in table.get_text():
                rows = table.find_all('tr')
                if len(rows) > 1:
                    headers = [cell.get_text(strip=True) for cell in rows[0].find_all('td')]
                    for row in rows[1:]:
                        values = [cell.get_text(strip=True) for cell in row.find_all('td')]
                        subject = dict(zip(headers, values))
                        subjects.append(subject)
                break
        return subjects

    def parse_student_results(self, soup):
        students = []
        tables = soup.find_all('table')
        for table in tables:
            if 'CNO' in table.get_text() and 'SEX' in table.get_text() and 'AGGT' in table.get_text() and 'DIV' in table.get_text() and 'DETAILED SUBJECTS' in table.get_text():
                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header
                    cells = row.find_all('td')
                    if len(cells) >= 5:
                        cno = cells[0].get_text(strip=True)
                        sex = cells[1].get_text(strip=True)
                        aggt = cells[2].get_text(strip=True)
                        div = cells[3].get_text(strip=True)
                        subjects = cells[4].get_text(strip=True)
                        students.append({
                            'CNO': cno,
                            'SEX': sex,
                            'AGGT': aggt,
                            'DIV': div,
                            'DETAILED SUBJECTS': subjects
                        })
                break
        return students

    def parse_school_region(self, soup, school_name):
        # Try to extract region from the page content
        text = soup.get_text()
        
        # Common Tanzanian regions to look for
        tanzania_regions = [
            "Dar es Salaam", "Arusha", "Dodoma", "Mwanza", "Mbeya", "Tanga", "Morogoro",
            "Kagera", "Mtwara", "Kilimanjaro", "Tabora", "Singida", "Rukwa", "Kigoma",
            "Shinyanga", "Mara", "Manyara", "Ruvuma", "Lindi", "Pwani", "Geita", "Katavi",
            "Njombe", "Simiyu", "Songwe", "Iringa", "Mjini Magharibi", "Unguja Kaskazini ", "Unguja Kusini", "Pemba Kaskazini", "Pemba Kusini"
        ]
        
        # Look for region patterns in the text
        region = "Unknown"
        for reg in tanzania_regions:
            if reg.lower() in text.lower():
                region = reg
                break
        
        # If region not found in text, try to infer from school name
        if region == "Unknown":
            for reg in tanzania_regions:
                if reg.lower() in school_name.lower():
                    region = reg
                    break
        
        return region

    def handle(self, *args, **options):
        exam = options["exam"].lower()
        year = options["year"]

        if exam not in ["csee", "acsee"]:
            raise CommandError("Only CSEE and ACSEE are supported.")

        index_url = f"{BASE_URL.format(year=year, exam=exam)}/index.htm"
        self.stdout.write(f"Fetching index: {index_url}")

        try:
            resp = requests.get(index_url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            raise CommandError(f"Failed to fetch {index_url}: {e}")

        soup = BeautifulSoup(resp.text, "html.parser")
        
        valid_links = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if (href.endswith('.htm') and 
                not href.startswith('index_') and
                not href == 'index.htm' and
                not 'indexfiles' in href):
                valid_links.append(link)
        
        if not valid_links:
            with open("debug_page.html", "w", encoding="utf-8") as f:
                f.write(resp.text)
            raise CommandError("No school result links found. The page structure may have changed. Saved page content to debug_page.html for inspection.")

        self.stdout.write(f"Found {len(valid_links)} schools. Scraping results...")

        all_results = []

        for link in valid_links:
            href = link["href"]
            href = href.replace('\\', '/')
            
            if href.startswith(('http://', 'https://')):
                school_url = href
            else:
                school_url = f"{BASE_URL.format(year=year, exam=exam)}{href}"
            
            school_text = link.text.strip()

            parts = school_text.split(maxsplit=1)
            if len(parts) < 2:
                code = os.path.splitext(href)[0].upper()
                name = school_text
            else:
                code, name = parts[0], parts[1]

            if 'index' in code.lower() or not code.startswith('S'):
                continue

            try:
                sresp = requests.get(school_url, timeout=30)
                sresp.raise_for_status()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️ Failed to fetch {school_url}: {e}"))
                continue

            ssoup = BeautifulSoup(sresp.text, "html.parser")
            
            div_counts = self.parse_division_summary(ssoup)
            overall = self.parse_overall_performance(ssoup)
            division_perf = self.parse_division_performance(ssoup)
            subjects = self.parse_subjects_performance(ssoup)
            students = self.parse_student_results(ssoup)
            
            # Extract region information
            region = self.parse_school_region(ssoup, name)
            
            gpa_str = overall.get('EXAMINATION CENTRE GPA', '')
            gpa_match = re.search(r'([\d.]+)', gpa_str)
            gpa = float(gpa_match.group(1)) if gpa_match else None
            
            if gpa is None:
                self.stdout.write(self.style.WARNING(f"⚠️ GPA not found for {code} {name}, skipping."))
                continue

            total = int(division_perf.get('CLEAN', sum(div_counts.values()))) or 1

            school, _ = School.objects.get_or_create(
                code=code, 
                defaults={
                    "name": name,
                    "region": region
                }
            )
            
            # Update region if it was previously unknown
            if school.region == "Unknown" and region != "Unknown":
                school.region = region
                school.save()

            ExamResult.objects.update_or_create(
                school=school,
                exam=exam.upper(),
                year=year,
                defaults={
                    "division1": div_counts["I"],
                    "division2": div_counts["II"],
                    "division3": div_counts["III"],
                    "division4": div_counts["IV"],
                    "division0": div_counts["0"],
                    "total": total,
                    "gpa": gpa,
                },
            )

            # Store result for ranking later
            all_results.append({
                "code": code,
                "name": name,
                "region": region,
                "gpa": gpa,
                "div1": div_counts["I"],
                "div2": div_counts["II"],
                "div3": div_counts["III"],
                "div4": div_counts["IV"],
                "div0": div_counts["0"],
                "total": total
            })

            self.stdout.write(f" → {code} {name} (Region: {region}, Div I: {div_counts['I']}, II: {div_counts['II']}, III: {div_counts['III']}, IV: {div_counts['IV']}, 0: {div_counts['0']}, Total: {total}, GPA: {gpa})")

        self.stdout.write(self.style.SUCCESS("✅ Scraping finished."))

        # Rank schools by GPA
        all_results.sort(key=lambda x: x["gpa"])
        self.stdout.write("\nRanking schools by GPA (lower is better):")
        for rank, result in enumerate(all_results, start=1):
            self.stdout.write(f"{rank}. {result['code']} {result['name']} (Region: {result['region']}) - GPA: {result['gpa']}")

        # Save results to a text file
        with open(f"school_results_{year}_{exam}.txt", "w", encoding="utf-8") as f:
            f.write("Rank. School Code School Name - Region - GPA\n")
            f.write("="*80 + "\n")
            for rank, result in enumerate(all_results, start=1):
                f.write(f"{rank}. {result['code']} {result['name']} - {result['region']} - GPA: {result['gpa']}\n")

        self.stdout.write(self.style.SUCCESS(f"✅ Results saved to school_results_{year}_{exam}.txt")) 