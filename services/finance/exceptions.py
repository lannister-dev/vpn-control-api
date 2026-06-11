class FinanceError(Exception):
    pass


class ExpenseNotFound(FinanceError):
    pass


class TemplateNotFound(FinanceError):
    pass
