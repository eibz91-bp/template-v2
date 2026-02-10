# crear controller -> se le injecta el use case  y el use case se le injecta el repositorio / servicio 

# singleton de cada use case 


from use_case.create_loan import CreateLoan
from controller.create_loan import CreateLoanController

create_loan_controller = CreateLoanController(CreateLoan())



# fast api 
# cqrs
# logging
# metrics
# tracing
# caching
# env
# call backs revisar 
# 
