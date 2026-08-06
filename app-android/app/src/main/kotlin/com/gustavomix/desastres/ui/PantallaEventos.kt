package com.gustavomix.desastres.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.gustavomix.desastres.core.Evento
import com.gustavomix.desastres.core.NivelAlerta
import com.gustavomix.desastres.core.TipoEvento

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PantallaEventos(viewModel: EventosViewModel) {
    val estado by viewModel.estado.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(title = { Text("Desastres naturales") })
        },
    ) { relleno ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(relleno),
        ) {
            estado.frescura.mensaje()?.let { mensaje ->
                AvisoFrescura(mensaje, estado.frescura.colorAviso())
            }

            when {
                estado.cargando -> Centrado { CircularProgressIndicator() }

                estado.error != null -> Centrado {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            text = "No se pudieron cargar los datos.",
                            style = MaterialTheme.typography.bodyLarge,
                        )
                        Text(
                            text = estado.error.orEmpty(),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        TextButton(onClick = viewModel::refrescar) { Text("Reintentar") }
                    }
                }

                else -> Column {
                    Filtros(estado, viewModel)
                    if (estado.vacioPorFiltros) {
                        Centrado {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text("Ningún evento coincide con los filtros.")
                                TextButton(onClick = viewModel::limpiarFiltros) {
                                    Text("Limpiar filtros")
                                }
                            }
                        }
                    } else {
                        ListaEventos(estado.eventos)
                    }
                }
            }
        }
    }
}

@Composable
private fun AvisoFrescura(mensaje: String, color: Color) {
    // No es decoración: en una app de desastres, mostrar datos viejos como si
    // fueran actuales es peor que no mostrar nada.
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 8.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(10.dp)
                .clip(CircleShape)
                .background(color),
        )
        Spacer(Modifier.width(10.dp))
        Text(text = mensaje, style = MaterialTheme.typography.bodySmall)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Filtros(estado: EstadoPantalla, viewModel: EventosViewModel) {
    Column(modifier = Modifier.padding(horizontal = 12.dp)) {
        OutlinedTextField(
            value = estado.filtro.texto,
            onValueChange = viewModel::buscar,
            label = { Text("Buscar lugar o país") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            estado.conteoPorTipo.entries
                .sortedByDescending { it.value }
                .forEach { (tipo, cantidad) ->
                    FilterChip(
                        selected = tipo in estado.filtro.tipos,
                        onClick = { viewModel.alternarTipo(tipo) },
                        label = { Text("${tipo.icono()} ${tipo.etiqueta()} $cantidad") },
                    )
                }
        }

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(bottom = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            listOf(
                NivelAlerta.SIN_DATO to "Todas",
                NivelAlerta.VERDE to "Verde+",
                NivelAlerta.NARANJA to "Naranja+",
                NivelAlerta.ROJA to "Solo rojas",
            ).forEach { (nivel, etiqueta) ->
                FilterChip(
                    selected = estado.filtro.alertaMinima == nivel,
                    onClick = { viewModel.cambiarAlertaMinima(nivel) },
                    label = { Text(etiqueta) },
                    colors = FilterChipDefaults.filterChipColors(),
                )
            }
        }

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(bottom = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            estado.paisesDisponibles.forEach { codigo ->
                FilterChip(
                    selected = codigo in estado.filtro.paises,
                    onClick = { viewModel.alternarPais(codigo) },
                    label = { Text(codigo) },
                )
            }
        }

        Text(
            text = "${estado.eventos.size} de ${estado.totalSinFiltrar} eventos",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun ListaEventos(eventos: List<Evento>) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items(eventos, key = { it.id }) { evento -> TarjetaEvento(evento) }
    }
}

@Composable
private fun TarjetaEvento(evento: Evento) {
    val estilo = EstiloAlerta.de(evento.alerta)

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(),
    ) {
        Row(modifier = Modifier.padding(14.dp)) {
            Text(
                text = evento.tipoEvento.icono(),
                modifier = Modifier.semantics {
                    contentDescription = evento.tipoEvento.etiqueta()
                },
            )
            Spacer(Modifier.width(12.dp))

            Column(modifier = Modifier.fillMaxWidth()) {
                Text(
                    text = evento.titulo,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium,
                )
                Spacer(Modifier.height(4.dp))

                Text(
                    text = buildString {
                        append(evento.fechaLegible())
                        evento.magnitudLegible?.let { append(" · ").append(it) }
                        if (evento.pais.isNotBlank()) append(" · ").append(evento.pais)
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )

                Spacer(Modifier.height(6.dp))

                // El nivel de alerta lleva SIEMPRE su etiqueta de texto: el
                // punto de color es refuerzo, no el mensaje.
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(9.dp)
                            .clip(CircleShape)
                            .background(estilo.color),
                    )
                    Spacer(Modifier.width(6.dp))
                    Text(
                        text = estilo.etiqueta,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun Centrado(contenido: @Composable () -> Unit) {
    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { contenido() }
}