class CreateLoanController:
    def __init__(self, use_case):
        self.use_case = use_case

    def execute(self, loan, request):
        validations.create_loan(loan) # validaciones de negocio validacion de la request / pydantic 
        self.use_case.create_loan(loan, request)
        return self.use_case.execute(loan, request)
    
    def disburse_loan(self, loan, request):
        provider_use_case = ProviderFactory(provider) ## objeto del tipo disburse DisburseLoanFactory
        validations.disburse_loan(loan)
        provider_use_case.execute(loan, request)
        #factory



class DisburseLoanFactory:

    abstractmethod
    def execute(self, provider):
        pass



class StpDisburseLoan:


    
    def execute(self, provider):
        pass

class NvioisburseLoan:

    
    def execute(self, provider):
        pass



#controller y user case no deben usar if 