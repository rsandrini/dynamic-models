#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from django.db import connection, DatabaseError
from django.db import models
from django.contrib.admin.sites import NotRegistered
from django.db.models.signals import class_prepared
from django.db.models.loading import cache as app_cache

from django.core.urlresolvers import clear_url_caches
from django.utils.importlib import import_module
from django.core.cache import cache
from django.conf import settings

import logging
from south.db import db

logger = logging.getLogger('surveymaker')


def unregister_from_admin(admin_site, model):
    " Remove o modelo dinâmico do site admin dado "

    # First deregister the current definition
    # This is done "manually" because model will be different
    # db_table is used to check for class equivalence.
    for reg_model in admin_site._registry.keys():
        if model._meta.db_table == reg_model._meta.db_table:
            del admin_site._registry[reg_model]

    # Try the normal approach too
    try:
        admin_site.unregister(model)
    except NotRegistered:
        pass

    # Reload the URL conf and clear the URL cache
    # It's important to use the same string as ROOT_URLCONF
    reload(import_module(settings.ROOT_URLCONF))
    clear_url_caches()


def reregister_in_admin(admin_site, model, admin_class=None):
    " (re) registra um modelo dinâmico no site admin dado "

    # Nós usamos o nosso unregister própria, para garantir que o correto
    # Modelo existente é encontrado
    # (Unregister Django não espera que a classe de modelo para mudar)
    unregister_from_admin(admin_site, model)
    admin_site.register(model, admin_class)

    # Reload the URL conf and clear the URL cache
    # It's important to use the same string as ROOT_URLCONF
    reload(import_module(settings.ROOT_URLCONF))
    clear_url_caches()


def when_classes_prepared(app_name, dependencies, fn):
    """ Executa a função administrada logo que as dependências do modelo estão disponíveis.
        Você pode usar isso para construir classes de modelo dyanmic na inicialização, em vez de
        tempo de execução.
        
        app_name o nome do app relevante
        dependências uma lista de nomes de modelos que precisam já ter sido
                       preparado antes das aulas dinâmicas podem ser construídas.
        fn este será chamado logo que os modelos de todos os necessários
                       Foram preparados
        
        NB: A fn será chamado logo que a requerida última
            modelo foi preparado. Isto pode acontecer no meio da leitura
            o arquivo models.py, antes de funções potencialmente referenciados têm
            foi carregado. Becaue esta função deve ser chamada antes de qualquer
            modelo relevante é definido, a única solução é atualmente a
            mover as funções necessárias antes que as dependências são declarados.
        
        TODO: Permitir dependências de outros aplicativos?
    """
    dependencies = [x.lower() for x in dependencies]

    def _class_prepared_handler(sender, **kwargs):
        """ Manipulador de sinal para class_prepared.
            Isto será executado para cada modelo, procurando o momento em que toda
            modelos dependentes são preparados pela primeira vez. Ela irá então executar
            a função dada, apenas uma vez.
        """
        sender_name = sender._meta.object_name.lower()
        already_prepared = set(app_cache.app_models.get(app_name,{}).keys() + [sender_name])

        if (sender._meta.app_label == app_name and sender_name in dependencies
          and all([x in already_prepared for x in dependencies])):
            db.start_transaction()
            try:
                fn()
            except DatabaseError:
                # If tables are  missing altogether, not much we can do
                # until syncdb/migrate is run. "The code must go on" in this 
                # case, without running our function completely. At least
                # database operations will be rolled back.
                db.rollback_transaction()
            else:
                db.commit_transaction()
                # TODO Now that the function has been run, should/can we 
                # disconnect this signal handler?
    
    # Ligue o manipulador acima, para o sinal de class_prepared
    # NB: Embora este sinal está documentado oficialmente, a documentação
    # Regista o seguinte:
    # "Django usa este sinal internamente, não é geralmente utilizado em
    # Aplicativos de terceiros. "
    class_prepared.connect(_class_prepared_handler, weak=False)


def get_cached_model(app_label, model_name, regenerate=False, get_local_hash=lambda i: i._hash):

    # If this model has already been generated, we'll find it here
    previous_model = models.get_model(app_label, model_name)

    # Before returning our locally cached model, check that it is still current
    if previous_model is not None and not regenerate:
        ##############CACHE_KEY = utils.HASH_CACHE_TEMPLATE % (app_label, model_name)
        CACHE_KEY = HASH_CACHE_TEMPLATE % (app_label, model_name)
        if cache.get(CACHE_KEY) != get_local_hash(previous_model):
            logging.debug("Local and shared dynamic model hashes are different: %s (local) %s (shared)" % (get_local_hash(previous_model), cache.get(CACHE_KEY)))
            regenerate = True

    # We can force regeneration by disregarding the previous model
    if regenerate:
        previous_model = None
        # Django keeps a cache of registered models, we need to make room for
        # our new one
        ###################utils.remove_from_model_cache(app_label, model_name)
        remove_from_model_cache(app_label, model_name)

    return previous_model


def remove_from_model_cache(app_label, model_name):
    """ Remove o modelo dado a partir do cache do modelo. """
    try:
        del app_cache.app_models[app_label][model_name.lower()]
    except KeyError:
        pass

def create_db_table(model_class):
    """ Toma uma classe de modelo Django e criar uma tabela de banco de dados, se necessário.
    """
    # XXX Create related tables for ManyToMany etc

    db.start_transaction()
    table_name = model_class._meta.db_table

    # Introspect the database to see if it doesn't already exist
    if (connection.introspection.table_name_converter(table_name) 
                        not in connection.introspection.table_names()):

        fields = _get_fields(model_class)

        db.create_table(table_name, fields)
        # Some fields are added differently, after table creation
        # eg GeoDjango fields
        db.execute_deferred_sql()
        logger.debug("Created table '%s'" % table_name)

    db.commit_transaction()


def delete_db_table(model_class):
    table_name = model_class._meta.db_table
    db.start_transaction()
    db.delete_table(table_name)
    logger.debug("Deleted table '%s'" % table_name)
    db.commit_transaction()


def _get_fields(model_class):
    """ Retorna uma lista de campos que requerem colunas da tabela. """
    return [(f.name, f) for f in model_class._meta.local_fields]


def add_necessary_db_columns(model_class):
    """ Cria nova tabela ou colunas pertinentes, se necessário com base no model_class.
         Sem colunas ou dados são renomeados ou removidos.
         Esta opção está disponível no caso de uma exceção de banco de dados ocorre.
    """
    db.start_transaction()

    # Create table if missing
    create_db_table(model_class)

    # Add field columns if missing
    table_name = model_class._meta.db_table
    fields = _get_fields(model_class)
    db_column_names = [row[0] for row in connection.introspection.get_table_description(connection.cursor(), table_name)]

    for field_name, field in fields:
        if field.column not in db_column_names:
            logger.debug("Adding field '%s' to table '%s'" % (field_name, table_name))
            db.add_column(table_name, field_name, field)


     # Algumas colunas necessitam de SQL adiada para ser executado. Este foi recolhido
     # Durante a execução db.add_column ().
    db.execute_deferred_sql()

    db.commit_transaction()


def rename_db_column(model_class, old_name, new_name):
    """ Renomear uma coluna de banco de dados do sensor. """
    table_name = model_class._meta.db_table
    db.start_transaction()
    db.rename_column(table_name, old_name, new_name) 
    logger.debug("Renamed column '%s' to '%s' on %s" % (old_name, new_name, table_name))
    db.commit_transaction()


def notify_model_change(model):
    """ Notifica outros processos que um modelo de dinâmica mudou.
         Isso só deve ser chamado após as alterações do banco de dados necessários foram feitos.
    """
    CACHE_KEY = HASH_CACHE_TEMPLATE % (model._meta.app_label, model._meta.object_name) 
    cache.set(CACHE_KEY, model._hash)
    logger.debug("Setting \"%s\" hash to: %s" % (model._meta.verbose_name, model._hash))


HASH_CACHE_TEMPLATE = 'dynamic_model_hash_%s-%s'
