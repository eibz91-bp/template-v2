# 

class CreateLoan:
 
    # no puede haber if 
    def execute(self, loan):
        
        user =self.repository.get_client_by_id(loan.client_id)
        
        user_exists(user)
        
        self.repository.create(loan)
        
        return loan

    def user_exists(self, user):
        if not user:
            raise ValueError("User not found")


class GetLoan:
    def execute(self, loan_id):
        return self.repository.get_loan_by_id(loan_id)


class d

class DisburseLoan:
    def __init__(self, get_loan: GetLoan, provider_factory: ProviderFactory):
        self.get_loan = get_loan
        self.provider_factory = provider_factory

    def execute(self, loan, request, provider):
        
        provider = self.provider_factory.get_provider(provider)
        loan = self.get_loan.execute(loan)
        
        disburse_provider = self.get_disburse_provider(request.provider)
        disburse_provider.disburse(loan)

class ScoreLoan:

    def __init__(self, get_loan: GetLoan):
        self.get_loan = get_loan

    def execute(self, loan):
        loan = self.get_loan.execute(loan)
        score = self.get_score_from_external_service(loan)
        socore_save = self.repository.score_loan(loan)

