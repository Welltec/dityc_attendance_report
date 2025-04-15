# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, _
from odoo.fields import Datetime, Date
import logging
from datetime import datetime, date
from lxml import etree
from psycopg2.extensions import AsIs
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AttendanceRealtimeCache(models.Model):
    _name = 'dityc.attendance.realtime.cache'
    _description = 'Cache de Asistencias en Tiempo Real'
    _order = 'fecha desc, employee_id, entrada'

    id = fields.Integer(string='ID')
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True)
    fecha = fields.Date(string='Fecha', required=True)
    dia_semana = fields.Char(string='Día')
    entrada = fields.Datetime(string='Entrada')
    salida = fields.Datetime(string='Salida')
    tipo_dia = fields.Selection([
        ('habil', 'Hábil'),
        ('sabado_am', 'Sáb AM'),
        ('sabado_pm', 'Sáb PM'),
        ('domingo', 'Dom'),
        ('feriado', 'Feriado'),
        ('no_laborable', 'No Lab.')
    ], string='Tipo')
    es_feriado = fields.Boolean(string='Feriado', default=False)
    nombre_feriado = fields.Char(string='Desc. Feriado')
    es_dia_laborable = fields.Boolean(string='Laborable', default=True,
        help="Indica si el empleado debe trabajar este día según su calendario")
    
    # Campos para horas trabajadas
    horas_semana_normal = fields.Float(string='Normal L-V', digits=(16, 2), default=0.0)
    horas_sabado_50 = fields.Float(string='50% Sáb', digits=(16, 2), default=0.0)
    horas_extra_100 = fields.Float(string='100% S/D', digits=(16, 2), default=0.0)
    horas_feriado = fields.Float(string='Hrs Feriado', digits=(16, 2), default=0.0)
    total_horas_trabajadas = fields.Float(string='Total Hrs', digits=(16, 2), default=0.0)
    horas_justificadas = fields.Float(string='Hrs Justificadas', digits=(16, 2), default=0.0)
    novedad_desc = fields.Char(string='Desc. Novedad')



    @api.model
    def _actualizar_cache_automatico(self):
        """Actualiza el caché con los datos más recientes de la vista"""
        try:
            _logger.info("Iniciando actualización automática del caché")
            
            # Verificar si la vista existe antes de continuar
            self.env.cr.execute("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.tables 
                    WHERE table_name = 'dityc_attendance_realtime_view'
                )
            """)
            view_exists = self.env.cr.fetchone()[0]
            
            if not view_exists:
                _logger.warning("La vista dityc_attendance_realtime_view aún no existe. Se omitirá la actualización del caché.")
                return False
            
            # Eliminar registros antiguos de manera segura
            self.env.cr.execute("TRUNCATE TABLE %s", (AsIs(self._table),))
            
            # Establecer la zona horaria para toda la sesión
            self.env.cr.execute("SET TIME ZONE 'America/Argentina/Buenos_Aires'")
            
            # Insertar nuevos registros desde la vista
            query = """
                INSERT INTO %s (
                    employee_id, company_id, fecha, dia_semana, 
                    entrada, salida, tipo_dia, es_feriado, nombre_feriado,
                    horas_semana_normal, horas_sabado_50, horas_extra_100, 
                    horas_feriado, total_horas_trabajadas, horas_justificadas, novedad_desc,
                    create_uid, create_date, write_uid, write_date
                )
                SELECT 
                    employee_id, company_id, fecha, dia_semana,
                    -- Convertir timestamps a naive (sin zona horaria)
                    entrada AT TIME ZONE 'UTC', 
                    salida AT TIME ZONE 'UTC',
                    tipo_dia, es_feriado, nombre_feriado,
                    horas_semana_normal, horas_sabado_50, horas_extra_100,
                    horas_feriado, total_horas_trabajadas, horas_justificadas, novedad_desc,
                    1, NOW() AT TIME ZONE 'UTC', 1, NOW() AT TIME ZONE 'UTC'
                FROM dityc_attendance_realtime_view
                -- Aseguramos que se obtengan todos los registros, incluso si no hay asistencias
                WHERE fecha >= (date_trunc('month', NOW()) - interval '2 month')::date
                  AND fecha <= (date_trunc('month', NOW() + interval '1 month') - interval '1 day')::date
                ORDER BY fecha, employee_id
            """
            self.env.cr.execute(query, (AsIs(self._table),))
            self.env.cr.commit()  # Commit explícito después de la inserción
            
            _logger.info("Caché actualizado exitosamente")
            return True
            
        except Exception as e:
            self.env.cr.rollback()  # Rollback explícito en caso de error
            _logger.error("Error en actualización automática del cache: %s", str(e))
            # No propagar el error, solo registrarlo
            return False

    def init(self):
        """Inicializa el modelo de caché"""
        super(AttendanceRealtimeCache, self).init()
        try:
            # Intentar actualizar el caché, pero no forzar el error si no se puede
            self._actualizar_cache_automatico()
        except Exception as e:
            _logger.error("Error durante la inicialización del caché: %s", str(e))
            # No propagar el error para permitir que continúe la instalación del módulo

    @api.model
    def actualizar_cache(self):
        """Actualiza el caché de asistencias en tiempo real"""
        try:
            _logger.info("Iniciando actualización manual del caché")
            
            # Verificar si la vista existe antes de continuar
            self.env.cr.execute("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.tables 
                    WHERE table_name = 'dityc_attendance_realtime_view'
                )
            """)
            view_exists = self.env.cr.fetchone()[0]
            
            if not view_exists:
                _logger.warning("La vista dityc_attendance_realtime_view aún no existe. Se omitirá la actualización del caché.")
                return False
            
            # Limpia el caché actual
            self._cr.execute('TRUNCATE TABLE %s' % self._table)
            
            # Establecer la zona horaria para toda la sesión
            self.env.cr.execute("SET TIME ZONE 'America/Argentina/Buenos_Aires'")
            
            # Enfoque más eficiente: inserción directa desde la vista
            query = """
                INSERT INTO %s (
                    employee_id, company_id, fecha, dia_semana, 
                    entrada, salida, tipo_dia, es_feriado, nombre_feriado,
                    horas_semana_normal, horas_sabado_50, horas_extra_100, 
                    horas_feriado, total_horas_trabajadas, es_dia_laborable,
                    horas_justificadas, novedad_desc,
                    create_uid, create_date, write_uid, write_date
                )
                SELECT 
                    v.employee_id, v.company_id, v.fecha, v.dia_semana,
                    -- Convertir timestamps a naive (sin zona horaria)
                    v.entrada AT TIME ZONE 'UTC', 
                    v.salida AT TIME ZONE 'UTC',
                    v.tipo_dia, v.es_feriado, v.nombre_feriado,
                    v.horas_semana_normal, v.horas_sabado_50, v.horas_extra_100,
                    v.horas_feriado, v.total_horas_trabajadas,
                    -- Determinar si es día laborable para cada empleado según su calendario
                    CASE WHEN e.resource_calendar_id IS NOT NULL THEN 
                        EXISTS (
                            SELECT 1 FROM resource_calendar_attendance rca 
                            WHERE rca.calendar_id = e.resource_calendar_id 
                            AND rca.dayofweek = EXTRACT(DOW FROM v.fecha)::text
                        )
                    ELSE TRUE END as es_dia_laborable,
                    v.horas_justificadas, v.novedad_desc,
                    1, NOW() AT TIME ZONE 'UTC', 1, NOW() AT TIME ZONE 'UTC'
                FROM dityc_attendance_realtime_view v
                JOIN hr_employee e ON v.employee_id = e.id
                WHERE v.fecha >= (date_trunc('month', NOW()) - interval '2 month')::date
                ORDER BY v.fecha, v.employee_id
            """
            
            self.env.cr.execute(query, (AsIs(self._table),))
            self.env.cr.commit()  # Commit explícito después de la inserción
            
            _logger.info("Caché actualizado exitosamente")
            return True
            
        except Exception as e:
            _logger.error(f"Error en actualizar_cache: {str(e)}")
            self._cr.rollback()
            raise

    @api.model
    def actualizar_cache_manual(self):
        """Método para actualizar el caché, llamado manualmente"""
        return self.actualizar_cache()

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        """Sobrescribe fields_view_get para agregar campos dinámicos a la vista"""
        result = super(AttendanceRealtimeCache, self).fields_view_get(
            view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        
        if view_type == 'tree':
            try:
                # Obtener el elemento tree
                doc = etree.XML(result['arch'])
                nodes = doc.xpath("//tree")
                if not nodes:
                    return result
                    
                tree = nodes[0]
                
                # Buscar el campo horas_trabajadas
                horas_node = tree.xpath("//field[@name='total_horas_trabajadas']")
                if horas_node:
                    insert_after = horas_node[0]
                else:
                    insert_after = tree[-1] if len(tree) > 0 else None
                
                # Agregar campos dinámicos después de total_horas_trabajadas
                if insert_after is not None:
                    # Agregar campo para exportar a Excel
                    export_field = etree.Element('field', {
                        'name': 'export_xlsx',
                        'widget': 'button',
                        'string': 'Exportar Excel',
                        'type': 'object',
                        'class': 'btn-primary'
                    })
                    insert_after.addnext(export_field)
                
                result['arch'] = etree.tostring(doc, encoding='unicode')
                _logger.info(f"Vista de caché modificada exitosamente: {result['arch']}")
            except Exception as e:
                _logger.error(f"Error modificando la vista de caché: {str(e)}")
        
        return result 

    def refresh_cache(self):
        """Actualiza el caché desde la vista en tiempo real"""
        try:
            self._actualizar_cache_automatico()
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
        except Exception as e:
            _logger.error("Error al actualizar el caché: %s", str(e))
            raise UserError(_("Error al actualizar el caché: %s") % str(e))

    def clear_cache_data(self):
        """Vacía la tabla de caché"""
        try:
            _logger.info("Iniciando limpieza de datos del caché")
            # Eliminar todos los registros del caché
            self.env.cr.execute("TRUNCATE TABLE %s", (AsIs(self._table),))
            # Mostrar mensaje de éxito
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Éxito'),
                    'message': _('El caché ha sido vaciado correctamente.'),
                    'type': 'success',
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    },
                }
            }
        except Exception as e:
            _logger.error("Error al vaciar el caché: %s", str(e))
            raise UserError(_("Error al vaciar el caché: %s") % str(e))

    def export_xlsx(self):
        """Exporta los datos a Excel"""
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/export/xlsx_attendance_report',
            'target': 'self',
        } 