package com.contador.app

import android.os.Bundle
import android.view.WindowManager
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    private var count = 0
    private lateinit var counterText: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        // Mantiene la pantalla encendida mientras se cuenta.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        counterText = findViewById(R.id.counterText)
        count = getPreferences(MODE_PRIVATE).getInt(KEY_COUNT, 0)
        render()

        findViewById<Button>(R.id.countButton).setOnClickListener {
            count++
            save()
            render()
        }

        findViewById<Button>(R.id.resetButton).setOnClickListener {
            if (count == 0) return@setOnClickListener
            AlertDialog.Builder(this)
                .setMessage(R.string.reset_confirm)
                .setPositiveButton(R.string.reset) { _, _ ->
                    count = 0
                    save()
                    render()
                }
                .setNegativeButton(R.string.cancel, null)
                .show()
        }
    }

    private fun render() {
        counterText.text = count.toString()
    }

    private fun save() {
        getPreferences(MODE_PRIVATE).edit().putInt(KEY_COUNT, count).apply()
    }

    private companion object {
        const val KEY_COUNT = "count"
    }
}
