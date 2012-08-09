Runtime dynamic models with Django
==================================

Este é um projecto exemplo para demonstrar um certo número de técnicas que permitem
modelos dinâmicos para trabalhar.
Isto foi escrito para acompanhar uma conversa em 2011 Djangocon.eu, o texto do
Discussão é fornecido em `documentação deste projeto <http://dynamic-models.readthedocs.org/>` _ e um vídeo
da apresentação `pode ser encontrada aqui <http://2011.djangocon.eu/talks/22/>` _.

O projeto é uma fabricante de pesquisa simples, onde os usuários administrador pode definir pesquisas.
As respostas podem então ser armazenados numa tabela personalizado para que levantamento,
possível com um modelo dinâmico para cada pesquisa. Tabelas são migrados
quando são feitas alterações relevantes, usando um cache compartilhado de manter várias
processos em sincronia.

Isto foi escrito razoavelmente rápido, mas os esforços foram feitos para mantê-lo simples.
Haverá, sem dúvida, erros e bugs, talvez até mesmo alguns problemas conceituais.
Por favor, forneça qualquer feedback que você pode ter e eu vou ser feliz para melhorar esta
implementação. O objetivo deste projeto é demonstrar que os modelos dinâmicos
são possíveis e podem ser posto a funcionar de forma fiável.