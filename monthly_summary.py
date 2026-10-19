# monthly_summary.py
class MonthlySummary:
    def __init__(self, records):
        self.records = list(records)

    def get_total_records(self):
        return len(self.records)

    def calculate_average_systolic(self):
        if not self.records:
            return 0
        return sum(record.get_systolic() for record in self.records) / len(self.records)

    def calculate_average_diastolic(self):
        if not self.records:
            return 0
        return sum(record.get_diastolic() for record in self.records) / len(self.records)

    def calculate_average_pulse(self):
        pulse_rates = [
            record.get_pulse_rate()
            for record in self.records
            if isinstance(record.get_pulse_rate(), int)
        ]
        if not pulse_rates:
            return 0
        return sum(pulse_rates) / len(pulse_rates)
